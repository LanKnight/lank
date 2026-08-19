"""
agent/executor.py - ACT 阶段（design.md §5.3）

每步独立紧凑上下文：目标 + 当前步 + 前步摘要 + 本轮消息。
绝不复用整段会话历史。
"""

from typing import Optional

from ..logs import get_logger
from ..tools import get_tool_descriptions
from .prompts import get_exec_prompt
from .types import Plan, Step, StepStatus

logger = get_logger("agent.executor")


class Executor:
    """按计划逐步执行器"""

    def __init__(self, client, callbacks):
        self.client = client
        self.callbacks = callbacks

    def execute_plan(self, plan: Plan) -> None:
        """按顺序执行计划中的未完成步骤（含被 review 追加的新步骤）"""
        # 只执行 PENDING（BLOCKED 步骤由 loop 判定终止，不在此自动重试）
        pending = [s for s in plan.steps if s.status == StepStatus.PENDING]
        prev_summary = self._last_done_summary(plan)

        for step in pending:
            step.status = StepStatus.IN_PROGRESS
            if self.callbacks and self.callbacks.on_step_progress:
                self.callbacks.on_step_progress(step, "start")
            self._execute_step(plan, step, prev_summary)
            if step.status == StepStatus.DONE and step.summary:
                prev_summary = step.summary
            if self.callbacks and self.callbacks.on_step_progress:
                self.callbacks.on_step_progress(step, "end")

    def _last_done_summary(self, plan: Plan) -> str:
        for s in reversed(plan.steps):
            if s.status == StepStatus.DONE and s.summary:
                return s.summary
        return ""

    def _execute_step(self, plan: Plan, step: Step, prev_summary: str) -> None:
        total = len(plan.steps)
        index = plan.steps.index(step) + 1

        exec_prompt = get_exec_prompt(
            goal=plan.goal,
            step_index=index,
            step_total=total,
            step_id=step.id,
            step_title=step.title,
            step_action=step.action,
            step_acceptance=step.acceptance,
            prev_summary=prev_summary,
        )
        prompt = exec_prompt + "\n\n" + get_tool_descriptions()

        messages = [{"role": "user", "content": f"请开始执行步骤 #{step.id}：{step.title}"}]

        def on_tool_call(name, args, result=None):
            if self.callbacks and self.callbacks.on_tool_call:
                return self.callbacks.on_tool_call(name, args, result)
            return True

        def on_text(text):
            if self.callbacks and self.callbacks.on_text:
                self.callbacks.on_text(text)

        try:
            success, final_text, _ = self.client.chat(
                messages=messages,
                stream=True,
                on_tool_call=on_tool_call,
                on_text=on_text,
            )
        except Exception as e:
            logger.exception("步骤 #%d 执行异常", step.id)
            step.status = StepStatus.BLOCKED
            step.summary = f"执行异常: {e}"
            return

        if not success:
            # chat 请求失败（网络/API），明确标记受阻
            logger.warning("步骤 #%d 请求失败: %.150s", step.id, final_text)
            step.status = StepStatus.BLOCKED
            step.summary = (final_text or "执行请求失败")[:200]
            return

        # step_done 工具已在工具循环中标记步骤完成
        if step.status == StepStatus.IN_PROGRESS:
            # 模型未调用 step_done 就结束 → 视为未完成
            reason = (final_text or "").strip()[:200]
            step.status = StepStatus.BLOCKED
            step.summary = reason or "步骤未登记完成"
            logger.warning("步骤 #%d 未登记完成，标记 blocked", step.id)
