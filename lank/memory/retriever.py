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
    """重要性：显式记忆 > 自动抽取；提及次数加成"""
    source = entry.get("source", "auto")
    base = 3.0 if source == "explicit" else 1.0
    mentions = float(entry.get("mention_count", 1))
    return base + (mentions - 1) * 0.5


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
    """获取注入 AI 提示词的相关记忆文本（「提前的加载」）"""
    if top_k is None:
        top_k = int(get_config("memory_top_k", 5))

    lines: List[str] = []

    # 用户画像（总是注入）
    try:
        from .store import get_profile_summary
        profile = get_profile_summary()
        if profile:
            lines.append(profile)
    except Exception:
        pass

    # 相关记忆
    results = search_memories(query, top_k) if query else []
    if not query:
        # 无查询词：退回最近摘要（会话启动默认加载）
        summaries = load_summaries()
        recent = sorted(
            summaries.values(),
            key=lambda s: s.get("timestamp", ""),
            reverse=True,
        )[:2]
        results = [{
            "kind": "summary",
            "text": s.get("summary", ""),
            "timestamp": s.get("timestamp", ""),
        } for s in recent if s.get("summary")]

    if results:
        lines.append("\n## 相关记忆")
        for r in results:
            tag = "📜" if r.get("kind") == "summary" else "🧠"
            lines.append(f"- {tag} {r.get('text', '')}")

    return "\n".join(lines)
