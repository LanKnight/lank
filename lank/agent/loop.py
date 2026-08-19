"""
agent/loop.py - AgentLoop 主循环（design.md §5.5）

状态机：分类 → PLAN → ACT → REVIEW（可迭代）→ DONE
控制：步骤上限、review 迭代上限、用户中断、auto 模式。
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..config import get_config
from ..logs import get_logger
from .context import set_current_loop
from .executor import Executor
from .planner import Planner
from .reviewer import Reviewer
from .types import (
    AgentPhase,
    AgentResult,
    Plan,
    PlanStatus,
    ReviewVerdict,
    StepStatus,
)

logger = get_logger("agent.loop")


@dataclass
class AgentCallbacks:
    """UI 层回调（cli / tui 实现）"""
    on_text: Optional[Callable] = None            # (text) 流式文本
    on_tool_call: Optional[Callable] = None       # (name, args, result=None) -> bool
    on_plan_render: Optional[Callable] = None     # (plan) 展示计划
    on_plan_confirm: Optional[Callable] = None    # (plan) -> bool 用户确认
    on_step_progress: Optional[Callable] = None   # (step, phase: "start"/"end")
    on_review: Optional[Callable] = None          # (verdict) 展示审核结果
    on_review_confirm: Optional[Callable] = None  # (verdict) -> bool 用户终审
    on_ask_user: Optional[Callable] = None        # (question, options) -> str


class AgentLoop:
    """Plan → Act → Review 状态机"""

    def __init__(self, client, callbacks: Optional[AgentCallbacks] = None):
        self.client = client
        self.callbacks = callbacks or AgentCallbacks()
        self.plan: Optional[Plan] = None
        self._pending_plan: Optional[Plan] = None
        self._pending_verdict: Optional[ReviewVerdict] = None

    def _next_step_id(self) -> int:
        if not self.plan:
            return 1
        return max((s.id for s in self.plan.steps), default=0) + 1

    def run(self, user_input: str, memory_text: str = "") -> AgentResult:
        """执行一次完整的 plan → act → review 流程

        Args:
            user_input: 用户输入
            memory_text: 注入的记忆上下文（由调用方构建，可选）

        Returns:
            AgentResult
        """
        set_current_loop(self)
        try:
            # ── 1. 分类 + 规划 ──
            planner = Planner(
                self.client,
                memory_text=memory_text,
                on_text=self.callbacks.on_text,
                on_tool_call=self.callbacks.on_tool_call,
            )
            success, answer, plan = planner.plan_or_answer(user_input)
            if not success:
                return AgentResult(False, answer, phase=AgentPhase.DONE)
            if plan is None:
                # 简单问答：直接回答，不进框架
                return AgentResult(True, answer, phase=AgentPhase.CLASSIFY)

            self.plan = plan
            plan.status = PlanStatus.CREATED

            # ── 2. 计划确认 ──
            if self.callbacks.on_plan_render:
                self.callbacks.on_plan_render(plan)
            confirmed = True
            auto = bool(get_config("auto_mode", False))
            if not auto and self.callbacks.on_plan_confirm:
                confirmed = self.callbacks.on_plan_confirm(plan)
            if not confirmed:
                plan.status = PlanStatus.ABANDONED
                return AgentResult(False, "任务已取消", phase=AgentPhase.PLAN, plan=plan)
            plan.status = PlanStatus.RUNNING

            # ── 3. 执行 + 4. 审核（可迭代） ──
            executor = Executor(self.client, self.callbacks)
            reviewer = Reviewer(self.client)
            max_review = int(get_config("max_review_rounds", 3))

            for _ in range(max_review + 1):
                executor.execute_plan(plan)

                if not all(s.status == StepStatus.DONE for s in plan.steps):
                    break  # 存在 blocked 步骤，无法继续

                verdict = reviewer.review(plan)
                if verdict is None:
                    # 审核失败：直接交付当前结果
                    plan.status = PlanStatus.FINISHED
                    return AgentResult(
                        True, self._summarize(plan),
                        phase=AgentPhase.REVIEW, plan=plan,
                    )

                if self.callbacks.on_review:
                    self.callbacks.on_review(verdict)

                if verdict.deliverable:
                    plan.status = PlanStatus.FINISHED
                    text = verdict.summary or self._summarize(plan)
                    # 用户终审（auto 模式直接通过）
                    if auto or self.callbacks.on_review_confirm is None \
                            or self.callbacks.on_review_confirm(verdict):
                        return AgentResult(True, text, phase=AgentPhase.REVIEW, plan=plan)
                    # 用户终审不通过 → 追加人工补充说明
                    return AgentResult(True, text, phase=AgentPhase.REVIEW, plan=plan)

                # 未达标：追加新步骤，继续执行
                if verdict.new_steps:
                    existing_ids = {s.id for s in plan.steps}
                    for s in verdict.new_steps:
                        if s.id not in existing_ids:
                            plan.steps.append(s)
                            existing_ids.add(s.id)
                    logger.info("审核未达标，追加 %d 个新步骤", len(verdict.new_steps))
                    continue
                break  # 无新步骤可做

            # ── 超限或受阻 ──
            plan.status = PlanStatus.FINISHED
            all_done = all(s.status == StepStatus.DONE for s in plan.steps)
            return AgentResult(
                all_done,
                self._summarize(plan),
                phase=AgentPhase.REVIEW,
                plan=plan,
            )

        finally:
            set_current_loop(None)

    def _summarize(self, plan: Plan) -> str:
        lines = [f"📋 任务「{plan.goal}」执行结束", ""]
        done = [s for s in plan.steps if s.status == StepStatus.DONE]
        blocked = [s for s in plan.steps if s.status == StepStatus.BLOCKED]
        lines.append(f"完成 {len(done)}/{len(plan.steps)} 步：")
        for s in done:
            lines.append(f"  ✅ {s.title}")
            if s.summary:
                lines.append(f"     结果: {s.summary[:100]}")
        for s in blocked:
            lines.append(f"  ⛔ {s.title}（{s.summary[:60]}）")
        return "\n".join(lines)
