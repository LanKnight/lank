"""
记忆工具 - 供 AI 主动调用（RAG 风格，design.md §8.7）
memory_search / memory_recall / memory_remember / memory_forget
"""

from typing import Optional

from ..memory import add_fact, remove_fact, search_facts, search_memories
from . import register_tool


def _format_results(results) -> str:
    if not results:
        return "（未找到相关记忆）"
    lines = [f"找到 {len(results)} 条相关记忆:", ""]
    for r in results:
        tag = "📜" if r.get("kind") == "summary" else "🧠"
        lines.append(f"- {tag} {r.get('text', '')}")
    return "\n".join(lines)


def memory_search(query: str, top_k: int = 5) -> str:
    """检索相关历史会话与长期事实"""
    results = search_memories(query, top_k)
    return _format_results(results)


def memory_recall(topic: str, top_k: int = 5) -> str:
    """召回某主题的长期事实（语义记忆）"""
    results = search_facts(topic, top_k)
    return _format_results(results)


def memory_remember(fact: str, importance: int = 1) -> str:
    """显式记住一条事实（写入长期记忆）"""
    if not fact or not fact.strip():
        return "错误: 事实内容为空"
    fact_id = add_fact(fact.strip(), source="explicit", importance=max(1, min(3, importance)))
    return f"✅ 已记住: {fact.strip()} (id: {fact_id})"


def memory_forget(fact_id: str) -> str:
    """删除一条长期记忆"""
    if remove_fact(fact_id):
        return f"🗑️ 已遗忘记忆: {fact_id}"
    return f"❌ 未找到记忆: {fact_id}"


# ── 注册工具 ──

register_tool(
    name="memory_search",
    description="检索相关的历史对话与长期记忆（主动回忆用）",
    func=memory_search,
    parameters=[
        {"name": "query", "type": "string", "description": "检索关键词"},
        {"name": "top_k", "type": "integer", "description": "返回条数", "required": False},
    ],
    category="memory",
    danger_level=0,
)

register_tool(
    name="memory_recall",
    description="召回某主题的长期事实（用户偏好/项目信息等）",
    func=memory_recall,
    parameters=[
        {"name": "topic", "type": "string", "description": "主题关键词"},
        {"name": "top_k", "type": "integer", "description": "返回条数", "required": False},
    ],
    category="memory",
    danger_level=0,
)

register_tool(
    name="memory_remember",
    description="显式记住一条关于用户的长期事实或偏好",
    func=memory_remember,
    parameters=[
        {"name": "fact", "type": "string", "description": "要记住的事实"},
        {"name": "importance", "type": "integer", "description": "重要性 1-3", "required": False},
    ],
    category="memory",
    danger_level=1,
    requires_approval=True,
)

register_tool(
    name="memory_forget",
    description="删除一条长期记忆",
    func=memory_forget,
    parameters=[
        {"name": "fact_id", "type": "string", "description": "记忆 id"},
    ],
    category="memory",
    danger_level=2,
    requires_approval=True,
)
