"""
agent/context.py - 当前 AgentLoop 上下文

工具函数（submit_plan / step_done / ask_user 等）是模块级注册函数，
需要通过本模块与运行中的 AgentLoop 通信。
"""

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .loop import AgentLoop

_current_loop: Optional["AgentLoop"] = None


def set_current_loop(loop: Optional["AgentLoop"]) -> None:
    """设置/清除当前运行的 AgentLoop"""
    global _current_loop
    _current_loop = loop


def get_current_loop() -> Optional["AgentLoop"]:
    """获取当前运行的 AgentLoop"""
    return _current_loop
