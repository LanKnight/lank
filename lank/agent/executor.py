"""
agent/executor.py - ACT 阶段（design.md §5.3）

每步独立紧凑上下文：目标 + 当前步 + 前步摘要 + 本轮消息。
绝不复用整段会话历史。
"""

import os
from datetime import datetime
from typing import Optional

from ..config import get_working_dir
from ..logs import get_logger
from ..tools import get_tool_descriptions
from .prompts import get_exec_prompt
from .types import Plan, Step, StepStatus

logger = get_logger("agent.executor")

# 模型明确表示无法继续的表述（用于放宽判定时区分"有产出"与"真受阻"）
_BLOCKED_HINTS = (
    "无法完成", "无法继续", "缺少必要", "需要用户", "无法访问",
    "遇到错误", "执行失败", "需要更多信息", "信息不足", "需要提供",
    "不能完成", "未找到", "没有权限",
)


def _looks_blocked(text: str) -> bool:
    return any(h in text for h in _BLOCKED_HINTS)


class Executor:
    """按计划逐步执行器"""

    def __init__(self, client, callbacks):
        self.client = client
        self.callbacks = callbacks

    def execute_plan(self, plan: Plan) -> None:
        """按顺序执行计划中的未完成步骤（含被 review 追加的新步骤）"""
        # 只执行 PENDING（BLOCKED 步骤交由 loop/review 决定补救）
        pending = [s for s in plan.steps if s.status == StepStatus.PENDING]
        prev_summary = self._last_done_summary(plan)

        for step in pending:
            step.status = StepStatus.IN_PROGRESS
            if self.callbacks and self.callbacks.on_step_progress:
                self.callbacks.on_step_progress(step, "start")
            self._execute_step(plan, step, prev_summary)
            if step.status == StepStatus.DONE and step.summary:
                prev_summary = step.summary
            self._write_progress(plan, step)
            if self.callbacks and self.callbacks.on_step_progress:
                self.callbacks.on_step_progress(step, "end")

    def _last_done_summary(self, plan: Plan) -> str:
        for s in reversed(plan.steps):
            if s.status == StepStatus.DONE and s.summary:
                return s.summary
        return ""

    def _write_progress(self, plan: Plan, step: Step) -> None:
        """把步骤进展追加到工作目录的进度文件（断点续传 / 人工查看中间产物）"""
        try:
            path = os.path.join(get_working_dir(), "lank_task_progress.md")
            icon = {StepStatus.DONE: "✅", StepStatus.BLOCKED: "⛔"}.get(step.status, "⏳")
            line = (
                f"## {icon} [{step.id}] {step.title}\n"
                f"- 任务: {plan.goal[:100]}\n"
                f"- 时间: {datetime.now().strftime('%H:%M:%S')}\n"
                f"- 验收: {step.acceptance}\n"
                f"- 结果: {step.summary[:500]}\n\n"
            )
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass  # 进度落盘失败不影响主流程

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
                system_prompt=prompt,  # EXEC_PROMPT + 工具描述
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
            # 模型未调用 step_done 就结束 → 放宽判定：
            # 有实质产出且未明确表示受阻 → 视为完成（保留产出），
            # 避免"没调 step_done 就白干"（方案2）
            reason = (final_text or "").strip()
            if _looks_blocked(reason):
                step.status = StepStatus.BLOCKED
                step.summary = reason[:200] or "步骤受阻"
            elif reason:
                step.status = StepStatus.DONE
                step.summary = reason[:200]
                logger.info("步骤 #%d 未调 step_done 但已产出实质内容，视为完成", step.id)
            else:
                step.status = StepStatus.BLOCKED
                step.summary = "步骤未登记完成（无产出）"
                logger.warning("步骤 #%d 无产出且未登记，标记 blocked", step.id)
