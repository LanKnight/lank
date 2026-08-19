"""
memory/forget.py - 遗忘器（design.md §8.3/§8.10）

时间衰减 + 容量上限 + 定期清理。
"""

from datetime import datetime, timedelta
from typing import Optional

from ..config import get_config
from ..logs import get_logger
from .store import (
    FACTS_FILE,
    HISTORY_DIR,
    SUMMARIES_FILE,
    atomic_write_json,
    ensure_memory_dir,
    load_facts,
    load_summaries,
)

logger = get_logger("memory.forget")


def cleanup_old_memories(max_days: int = 30) -> int:
    """清理超过 max_days 的原始会话与摘要

    Returns:
        清理的会话数
    """
    ensure_memory_dir()
    cutoff = datetime.now() - timedelta(days=max_days)
    cleaned = 0

    # 原始会话
    if HISTORY_DIR.exists():
        import json
        for f in HISTORY_DIR.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                ts = datetime.fromisoformat(data["timestamp"])
                if ts < cutoff:
                    f.unlink()
                    cleaned += 1
            except Exception:
                continue

    # 过期摘要
    summaries = load_summaries()
    changed = False
    for sid, entry in list(summaries.items()):
        try:
            ts = datetime.fromisoformat(entry.get("timestamp", ""))
            if ts < cutoff:
                del summaries[sid]
                changed = True
        except Exception:
            continue
    if changed:
        atomic_write_json(SUMMARIES_FILE, summaries)

    if cleaned:
        logger.info("清理旧记忆: %d 个会话", cleaned)
    return cleaned


def prune_facts(max_facts: Optional[int] = None) -> int:
    """语义记忆容量上限：超出时按 重要性×新鲜度 淘汰最不重要的

    Returns:
        淘汰的事实数
    """
    if max_facts is None:
        max_facts = int(get_config("memory_max_facts", 200))

    facts = load_facts()
    if len(facts) <= max_facts:
        return 0

    from .retriever import _freshness, _importance

    scored = []
    for fid, entry in facts.items():
        score = _importance(entry) * _freshness(entry.get("updated_at", ""))
        scored.append((score, fid))
    scored.sort()

    to_remove = len(facts) - max_facts
    for _, fid in scored[:to_remove]:
        del facts[fid]

    atomic_write_json(FACTS_FILE, facts)
    logger.info("事实容量整理: 淘汰 %d 条", to_remove)
    return to_remove
