"""
memory/extractor.py - 事实抽取器（design.md §8.5）

每会话结束后 LLM 抽取新事实/偏好 → 语义记忆（去重、冲突合并）。
显式记忆由 memory_remember 工具写入。
"""

import json
from typing import Any, Dict, List, Optional

from ..logs import get_logger

logger = get_logger("memory.extractor")

_EXTRACT_PROMPT = """从以下对话中提取关于用户的长期事实与偏好（画像信息）。

提取范围：
- 用户身份与环境（系统、工具链、项目、工作目录等）
- 用户偏好（回复风格、常用工具、习惯做法）
- 重要决定与承诺
- 值得长期记住的个人信息

不要提取：
- 一次性任务细节、临时数据
- 对话中的普通寒暄

输出 JSON 数组，每项为 {"text": "事实描述", "importance": 1-3}，
importance 3 为非常重要。只输出 JSON，不要其他文字。

对话内容：
{messages}"""


def extract_facts(messages: List[Dict[str, Any]], client=None) -> List[Dict[str, Any]]:
    """从对话中抽取事实（返回抽取到的事实列表）"""
    try:
        from ..ai_client import AIClient
        if client is None:
            client = AIClient()
            ready, _ = client.is_ready()
            if not ready:
                return []
        content = "\n".join(
            f"{m.get('role')}: {str(m.get('content', ''))[:300]}"
            for m in messages if m.get("role") in ("user", "assistant")
        )
        if len(content) < 20:
            return []
        prompt = _EXTRACT_PROMPT.format(messages=content[-6000:])
        # 抽取是次要功能：短超时 + 不重试，失败静默
        success, response, _ = client.complete(
            [{"role": "user", "content": prompt}],
            system_prompt="你是 LANK 的记忆抽取器，只输出 JSON。",
            timeout=8.0,
            retry=0,
        )
        if not success:
            return []
        facts = _parse_facts(response)
        return facts
    except Exception as e:
        logger.warning("事实抽取失败: %s", e)
        return []


def _parse_facts(response: str) -> List[Dict[str, Any]]:
    """解析 LLM 返回的 JSON 事实列表"""
    text = response.strip()
    # 去除可能的代码围栏
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [
                {"text": str(item.get("text", "")).strip(), "importance": int(item.get("importance", 1))}
                for item in data
                if isinstance(item, dict) and str(item.get("text", "")).strip()
            ]
    except json.JSONDecodeError:
        # 尝试提取 JSON 数组片段
        try:
            start, end = text.find("["), text.rfind("]")
            if start != -1 and end > start:
                data = json.loads(text[start:end + 1])
                if isinstance(data, list):
                    return [
                        {"text": str(item.get("text", "")).strip(), "importance": int(item.get("importance", 1))}
                        for item in data if isinstance(item, dict)
                    ]
        except json.JSONDecodeError:
            pass
    return []


def extract_and_update_profile(
    messages: List[Dict[str, Any]],
    client=None,
) -> int:
    """抽取事实并写入语义记忆（含去重合并）

    Returns:
        新增事实数
    """
    from .store import add_fact
    facts = extract_facts(messages, client=client)
    added = 0
    for f in facts:
        text = f.get("text", "")
        if text and len(text) <= 200:
            add_fact(text, source="auto", importance=f.get("importance", 1))
            added += 1
    if added:
        logger.info("画像更新: 新增/合并 %d 条事实", added)
    return added
