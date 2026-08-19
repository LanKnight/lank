"""
agent/planner.py - PLAN 阶段（design.md §5.1-§5.2）

分类 + 规划合并实现：
  - 模型能直接回答 → 流式输出纯文本（不进框架）
  - 模型调用 submit_plan → 工具循环中执行 → 解析为 Plan
零额外往返，利用原生 function calling 保证结构化输出。
"""

from typing import Callable, Optional, Tuple

from ..config import get_config
from ..logs import get_logger
from ..tools import get_tool_descriptions
from .context import get_current_loop
from .prompts import get_plan_prompt
from .types import Plan

logger = get_logger("agent.planner")


class Planner:
    """任务规划器：一次调用完成分类 + 规划（流式）"""

    def __init__(self, client, memory_text: str = "", on_text: Optional[Callable] = None):
        self.client = client
        self.memory_text = memory_text
        self.on_text = on_text

    def plan_or_answer(self, user_input: str) -> Tuple[bool, str, Optional[Plan]]:
        """分类 + 规划

        Returns:
            (success, answer_or_error, plan)
            - plan 为 None 时，answer 是直接回答（简单问答，已流式输出）
            - plan 非 None 时，进入 PLAN 阶段
        """
        max_steps = int(get_config("max_plan_steps", 10))
        plan_prompt = get_plan_prompt(max_steps)
        prompt = plan_prompt + "\n\n" + get_tool_descriptions()
        if self.memory_text:
            prompt += "\n\n" + self.memory_text

        messages = [{"role": "user", "content": user_input}]
        try:
            success, content, _ = self.client.chat(
                messages=messages,
                stream=True,
                on_tool_call=None,   # plan 工具均无需确认
                on_text=self.on_text,
            )
        except Exception as e:
            logger.exception("规划请求失败")
            return False, f"❌ 规划请求失败: {e}", None

        if not success:
            return False, content or "❌ 规划请求失败", None

        # ── 检查是否通过 submit_plan 提交了计划（工具循环已执行） ──
        loop = get_current_loop()
        if loop is not None and loop._pending_plan is not None:
            plan = loop._pending_plan
            loop._pending_plan = None
            logger.info("进入 PLAN 阶段: %s", plan.goal)
            return True, "", plan

        # ── 纯文本直接回答（已流式输出） ──
        return True, (content or "").strip(), None
