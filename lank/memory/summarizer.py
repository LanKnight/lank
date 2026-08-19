"""
memory/summarizer.py - 会话总结器（design.md §8.4）

总结时机：
  - 会话结束时：LLM 一次性生成摘要
  - 长会话中途：按 token 阈值增量滚动总结（分段压缩合并）
"""

from typing import Any, Dict, List, Optional

from ..config import get_config
from ..logs import get_logger

logger = get_logger("memory.summarizer")

_SUMMARY_PROMPT = """请为以下对话生成一段简洁的会话摘要（中文，不超过 {max_chars} 字）。

要求：
- 概括讨论的主题、做出的决定、产生的文件/代码、用户的偏好与需求；
- 保留关键事实（路径、命令、配置、结论）；
- 如果提供了旧摘要，在其基础上增量更新，不要重复旧内容。

旧摘要：
{prev_summary}

对话内容：
{messages}

只输出摘要本身，不要其他说明。"""


def _estimate_tokens(text: str) -> int:
    """粗略 token 估算：中文约 1 字/token，英文约 4 字符/token"""
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other = len(text) - cjk
    return cjk + other // 4


def _call_llm_summarize(messages: List[Dict[str, Any]], prev_summary: str, max_chars: int) -> Optional[str]:
    """调用 LLM 生成摘要（失败返回 None）"""
    try:
        from ..ai_client import AIClient
        client = AIClient()
        ready, _ = client.is_ready()
        if not ready:
            return None
        content = "\n".join(
            f"{m.get('role')}: {str(m.get('content', ''))[:500]}"
            for m in messages if m.get("role") in ("user", "assistant")
        )
        prompt = _SUMMARY_PROMPT.format(
            max_chars=max_chars,
            prev_summary=prev_summary[:1000] or "（无）",
            messages=content[-8000:],
        )
        success, response, _ = client.complete(
            [{"role": "user", "content": prompt}],
            system_prompt="你是 LANK 的记忆总结器。",
        )
        if success and response:
            return response.strip()[:max_chars * 2]
    except Exception as e:
        logger.warning("会话总结失败: %s", e)
    return None


def summarize_conversation(
    messages: List[Dict[str, Any]],
    client=None,
    prev_summary: str = "",
) -> Optional[str]:
    """生成会话摘要（可带旧摘要做增量滚动）

    Args:
        messages: 对话消息
        client: 可注入的 AI 客户端（默认自动创建）
        prev_summary: 已有摘要（长会话增量时传入）

    Returns:
        摘要文本，失败返回 None
    """
    if not messages:
        return None
    max_chars = int(get_config("memory_summary_max_chars", 2000))
    summary = _call_llm_summarize(messages, prev_summary, max_chars)
    return summary


def needs_rollup(messages: List[Dict[str, Any]], existing_summary: str = "") -> bool:
    """判断是否达到长会话增量总结阈值"""
    threshold = int(get_config("memory_long_session_threshold", 20000))
    text = "".join(str(m.get("content", "")) for m in messages)
    return _estimate_tokens(text) > threshold


def finalize_session(
    session_id: str,
    messages: List[Dict[str, Any]],
    client=None,
    prev_summary: str = "",
) -> Optional[str]:
    """会话结束时生成摘要并写入情景记忆

    Returns:
        摘要文本，失败返回 None
    """
    from datetime import datetime
    from .store import add_summary

    summary = summarize_conversation(messages, client=client, prev_summary=prev_summary)
    if summary:
        keywords = _extract_keywords(summary)
        add_summary(
            session_id=session_id,
            timestamp=datetime.now().isoformat(),
            summary=summary,
            keywords=keywords,
            messages_count=len(messages),
        )
        logger.info("会话 %s 摘要已写入", session_id)
    return summary


def _extract_keywords(text: str) -> List[str]:
    """简单关键词提取（供索引）"""
    import re
    words = re.findall(r"[a-zA-Z0-9_]{2,}", text.lower())
    cjk = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    seen, out = set(), []
    for w in words + cjk:
        if w not in seen and len(out) < 20:
            seen.add(w)
            out.append(w)
    return out
