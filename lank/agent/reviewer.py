"""
agent/reviewer.py - REVIEW 阶段（design.md §5.4）

对照验收标准（Plan.review_criteria + 各 Step.acceptance）逐条核对，
输出结构化判定 ReviewVerdict。
"""

from typing import Optional

from ..logs import get_logger
from ..tools import get_tool_descriptions
from .context import get_current_loop
from .prompts import get_review_prompt
from .types import Plan, ReviewVerdict, StepStatus

logger = get_logger("agent.reviewer")


class Reviewer:
    """交付审核器"""

    def __init__(self, client):
        self.client = client

    def review(self, plan: Plan) -> Optional[ReviewVerdict]:
        """审核计划是否可交付。返回 None 表示审核过程失败"""
        steps_text = self._format_steps(plan)
        review_prompt = get_review_prompt(plan.goal, plan.review_criteria, steps_text)
        prompt = review_prompt + "\n\n" + get_tool_descriptions()

        messages = [{"role": "user", "content": "请审核本任务是否可交付"}]
        try:
            success, _, messages = self.client.complete(messages, system_prompt=prompt)
        except Exception as e:
            logger.exception("审核请求失败")
            return None

        if not success:
            logger.warning("审核请求失败: %s", messages[-1].get("content", "") if messages else "")
            return None

        loop = get_current_loop()
        if loop and loop._pending_verdict:
            verdict = loop._pending_verdict
            loop._pending_verdict = None
            return verdict
        return None

    def _format_steps(self, plan: Plan) -> str:
        lines = []
        for i, s in enumerate(plan.steps, 1):
            icon = {StepStatus.DONE: "✅", StepStatus.BLOCKED: "⛔"}.get(s.status, "⬜")
            lines.append(f"[{i}] {icon} {s.title}")
            lines.append(f"    验收标准: {s.acceptance}")
            summary = s.summary or "（无结果）"
            lines.append(f"    结果: {summary[:200]}")
        return "\n".join(lines)
