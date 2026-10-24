"""
memory/retriever.py - 记忆检索器（design.md §8.6）

MVP：关键词加权检索（相关性 × 新鲜度 × 重要性），零新依赖。
预留向量接口：后续可替换为本地向量嵌入（fastembed）。
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..config import get_config
from .store import load_facts, load_summaries

_WORD_RE = re.compile(r"[a-zA-Z0-9_]+")


def _tokenize(text: str) -> set:
    """简单分词：英文单词 + 中文 2-gram"""
    tokens = set(_WORD_RE.findall(text.lower()))
    cjk = "".join(re.findall(r"[\u4e00-\u9fff]", text))
    if len(cjk) >= 2:
        tokens.update(cjk[i:i + 2] for i in range(len(cjk) - 1))
    return tokens


def _relevance(query_tokens: set, doc_tokens: set) -> float:
    """相关性：query token 在文档中的覆盖率"""
    if not query_tokens:
        return 0.0
    hits = query_tokens & doc_tokens
    return len(hits) / len(query_tokens)


def _freshness(timestamp: str, k: float = 0.1) -> float:
    """新鲜度：指数衰减 1/(1+age_days*k)"""
    try:
        ts = datetime.fromisoformat(timestamp)
        age_days = max(0.0, (datetime.now() - ts).total_seconds() / 86400.0)
    except Exception:
        age_days = 999.0
    return 1.0 / (1.0 + age_days * k)


def _importance(entry: Dict[str, Any]) -> float:
    """重要性：显式记忆 > 自动抽取；提及次数加成（封顶，防无关记忆反超相关结果）"""
    source = entry.get("source", "auto")
    base = 3.0 if source == "explicit" else 1.0
    mentions = float(entry.get("mention_count", 1))
    return min(base + (mentions - 1) * 0.5, 5.0)


def _weights() -> Tuple[float, float, float]:
    return (
        float(get_config("memory_relevance_weight", 0.4)),
        float(get_config("memory_freshness_weight", 0.3)),
        float(get_config("memory_importance_weight", 0.3)),
    )


def _score(query_tokens: set, text: str, entry: Dict[str, Any]) -> float:
    """综合评分：相关性主导，新鲜度/重要性仅在有相关性时加成"""
    w_rel, w_fresh, w_imp = _weights()
    rel = _relevance(query_tokens, _tokenize(text))
    fresh = _freshness(entry.get("timestamp", entry.get("updated_at", "")))
    imp = _importance(entry)
    if rel == 0:
        # 无相关性时大幅弱化，防止高重要性记忆在无关查询中反超
        return (fresh * w_fresh + imp * w_imp) * 0.1
    return rel * w_rel + fresh * w_fresh + imp * w_imp


def search_summaries(query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
    """检索会话摘要（情景记忆）"""
    if not query or not query.strip():
        return []  # 空查询不返回全部记忆
    if top_k is None:
        top_k = int(get_config("memory_top_k", 5))
    query_tokens = _tokenize(query)
    items = []
    for sid, entry in load_summaries().items():
        text = entry.get("summary", "")
        score = _score(query_tokens, text, entry)
        if score > 0:
            items.append({
                "kind": "summary",
                "session_id": sid,
                "timestamp": entry.get("timestamp", ""),
                "text": text[:200],
                "score": score,
            })
    items.sort(key=lambda x: x["score"], reverse=True)
    return items[:top_k]


def search_facts(query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
    """检索事实（语义记忆）"""
    if not query or not query.strip():
        return []  # 空查询不返回全部记忆
    if top_k is None:
        top_k = int(get_config("memory_top_k", 5))
    query_tokens = _tokenize(query)
    items = []
    for fid, entry in load_facts().items():
        text = entry.get("text", "")
        score = _score(query_tokens, text, entry)
        if score > 0:
            items.append({
                "kind": "fact",
                "fact_id": fid,
                "timestamp": entry.get("updated_at", ""),
                "text": text[:200],
                "source": entry.get("source", "auto"),
                "score": score,
            })
    items.sort(key=lambda x: x["score"], reverse=True)
    return items[:top_k]


def search_memories(query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
    """综合检索：摘要 + 事实"""
    if top_k is None:
        top_k = int(get_config("memory_top_k", 5))
    half = max(1, top_k // 2)
    results = search_summaries(query, half) + search_facts(query, half)
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def get_relevant_context(query: str = "", top_k: Optional[int] = None) -> str:
    """获取注入 AI 提示词的相关记忆文本（「提前的加载」）

    省 token 要点：
    - 尊重 memory_enabled 开关（关闭则完全不注入）；
    - 画像事实按 相关性×重要性×新鲜度 排序，只注入 Top-K，不再全量灌入；
    - 事实只在画像段出现、摘要只在该历史段出现，消除旧版“事实被重复注入”浪费；
    - 总长受 memory_max_inject_chars 安全封顶。
    """
    if not get_config("memory_enabled", True):
        return ""
    if top_k is None:
        top_k = int(get_config("memory_top_k", 5))
    profile_top_k = int(get_config("memory_profile_top_k", 12))

    lines: List[str] = []
    query_tokens = _tokenize(query)

    # 用户画像/长期事实：按得分排序取 Top-K（空查询时 relevance=0，自然退化为重要性×新鲜度排序）
    try:
        facts = load_facts()
        scored_facts = sorted(
            facts.items(),
            key=lambda kv: _score(query_tokens, kv[1].get("text", ""), kv[1]),
            reverse=True,
        )[:profile_top_k]
        if scored_facts:
            lines.append("\n## 用户画像与长期记忆")
            for _fid, entry in scored_facts:
                text = entry.get("text", "")
                if not text:
                    continue
                mark = "💾 " if entry.get("source") == "explicit" else ""
                lines.append(f"- {mark}{text[:160]}")
    except Exception:
        pass

    # 历史会话摘要（情景记忆）
    if query:
        summaries = [r for r in search_memories(query, top_k) if r.get("kind") == "summary"]
    else:
        recent = sorted(
            load_summaries().values(),
            key=lambda s: s.get("timestamp", ""),
            reverse=True,
        )[:2]
        summaries = [
            {"kind": "summary", "text": s.get("summary", "")[:200]}
            for s in recent if s.get("summary")
        ]
    if summaries:
        lines.append("\n## 相关历史会话")
        for r in summaries:
            lines.append(f"- 📜 {r.get('text', '')[:200]}")

    if not lines:
        return ""

    result = "\n".join(lines)
    # 总长安全封顶（保留开头，因最重要的画像/标题在前）
    max_chars = int(get_config("memory_max_inject_chars", 2500))
    if max_chars > 0 and len(result) > max_chars:
        result = result[:max_chars]
    return result
