"""
memory - 个性化记忆子系统（design.md §8）

原 memory.py 升级为包，对外 API 保持兼容：
  save_conversation / load_conversation / get_recent_context /
  get_profile / get_profile_summary / update_profile / cleanup_old_memories

新增能力：
  - 会话滚动摘要（summarizer）
  - 自动画像抽取（extractor）
  - 关键词加权检索（retriever）
  - 遗忘策略（forget）
"""

from typing import Any, Dict, List, Optional

from .store import (
    MEMORY_DIR,
    HISTORY_DIR,
    PROFILE_FILE,
    add_fact,
    add_procedure,
    add_summary,
    aggregate_profile,
    ensure_memory_dir,
    export_memories,
    get_profile,
    get_profile_summary,
    import_memories,
    list_sessions,
    load_conversation,
    load_facts,
    load_procedures,
    load_summaries,
    remove_fact,
    remove_procedure,
    save_conversation,
    update_profile,
)
from .retriever import (
    get_relevant_context,
    search_facts,
    search_memories,
    search_procedures,
    search_summaries,
)
from .summarizer import (
    finalize_session,
    needs_rollup,
    summarize_conversation,
)
from .extractor import (
    extract_and_update_profile,
    extract_facts,
)
from .forget import (
    cleanup_old_memories,
    prune_facts,
)

__all__ = [
    # store
    "save_conversation",
    "load_conversation",
    "list_sessions",
    "get_profile",
    "get_profile_summary",
    "update_profile",
    "add_fact",
    "remove_fact",
    "add_procedure",
    "remove_procedure",
    "load_procedures",
    "load_facts",
    "load_summaries",
    "add_summary",
    "aggregate_profile",
    "export_memories",
    "import_memories",
    "ensure_memory_dir",
    "MEMORY_DIR",
    "HISTORY_DIR",
    "PROFILE_FILE",
    # retriever
    "get_relevant_context",
    "search_memories",
    "search_summaries",
    "search_facts",
    "search_procedures",
    # summarizer
    "finalize_session",
    "needs_rollup",
    "summarize_conversation",
    # extractor
    "extract_and_update_profile",
    "extract_facts",
    # forget
    "cleanup_old_memories",
    "prune_facts",
]


def get_recent_context(max_sessions: int = 2) -> str:
    """兼容旧接口：返回最近会话摘要 + 用户画像"""
    summaries = load_summaries()
    recent = sorted(summaries.values(), key=lambda s: s.get("timestamp", ""), reverse=True)[:max_sessions]
    lines: List[str] = []
    profile = get_profile_summary()
    if profile:
        lines.append(profile)
    if recent:
        lines.append("\n## 历史对话记忆")
        for s in recent:
            ts = s.get("timestamp", "")[:16]
            lines.append(f"- 会话 {ts}: {s.get('summary', '')[:100]}")
    return "\n".join(lines)


def get_recent_conversations(days: int = 7) -> List[Dict[str, Any]]:
    """兼容旧接口：最近的会话列表"""
    return list_sessions(days)
