"""
memory/retriever.py - 记忆检索器（design.md §8.6）

MVP：关键词加权检索（相关性 × 新鲜度 × 重要性），零新依赖。
预留向量接口：后续可替换为本地向量嵌入（fastembed）。
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..config import get_config
from . import vector
from .store import load_facts, load_procedures, load_summaries

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


def _semantic_scores(query: str, docs: List[str]) -> Optional[List[float]]:
    """向量增强：返回每个 doc 与 query 的语义相关度(0~1)。

    未开启向量/后端不可用/失败时返回 None（调用方回退纯关键词）。默认关闭，
    因此不改变现有行为；开启后能让同义/跨表述的记忆也被召回。
    """
    if not docs or not vector.enabled():
        return None
    try:
        qv = vector.embed([query])
        dv = vector.embed(docs)
        if not qv or not dv or qv[0] is None:
            return None
        return [max(0.0, vector.cosine(qv[0], d)) for d in dv]
    except Exception:
        return None


def _score(query_tokens: set, text: str, entry: Dict[str, Any],
           sem: Optional[float] = None) -> float:
    """综合评分：相关性主导，新鲜度/重要性仅在有相关性时加成。

    sem 为可选语义相关度：与关键词相关性取较大，使无语词重叠但语义相近的记忆也能命中。
    """
    w_rel, w_fresh, w_imp = _weights()
    rel = _relevance(query_tokens, _tokenize(text))
    if sem is not None and sem > rel:
        rel = sem
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
    entries = list(load_summaries().items())
    texts = [e.get("summary", "") for _sid, e in entries]
    sems = _semantic_scores(query, texts)
    items = []
    for i, (sid, entry) in enumerate(entries):
        text = texts[i]
        score = _score(query_tokens, text, entry, sem=(sems[i] if sems else None))
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
    entries = list(load_facts().items())
    texts = [e.get("text", "") for _fid, e in entries]
    sems = _semantic_scores(query, texts)
    items = []
    for i, (fid, entry) in enumerate(entries):
        text = texts[i]
        score = _score(query_tokens, text, entry, sem=(sems[i] if sems else None))
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


def _procedure_doc_text(entry: Dict[str, Any]) -> str:
    parts = [str(entry.get("goal", ""))]
    for s in entry.get("steps", []):
        if isinstance(s, dict):
            parts.append(str(s.get("title", "")))
    return " ".join(p for p in parts if p)


def search_procedures(query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
    """检索可复用流程（程序性记忆），按 相关性×新鲜度×复用次数 排序"""
    if not query or not query.strip():
        return []
    if top_k is None:
        top_k = int(get_config("memory_procedure_top_k", 3))
    query_tokens = _tokenize(query)
    entries = list(load_procedures().items())
    texts = [_procedure_doc_text(e) for _pid, e in entries]
    sems = _semantic_scores(query, texts)
    items = []
    for i, (pid, entry) in enumerate(entries):
        score = _score(query_tokens, texts[i], entry, sem=(sems[i] if sems else None))
        # 复用次数作为附加信号（被反复成功使用的流程优先）
        score += min(float(entry.get("use_count", 1)) - 1.0, 3.0) * 0.05
        if score > 0:
            items.append({
                "kind": "procedure",
                "proc_id": pid,
                "goal": entry.get("goal", ""),
                "steps": entry.get("steps", []),
                "use_count": int(entry.get("use_count", 1)),
                "timestamp": entry.get("updated_at", ""),
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

    # 可复用流程（程序性记忆）：仅在有查询且开启时注入，作为规划参考
    if query and get_config("memory_procedural_enabled", True):
        try:
            procs = search_procedures(query)
            if procs:
                lines.append("\n## 可复用流程（过往成功套路）")
                lines.append("（若当前任务与下列目标相近，规划时请优先参考其步骤顺序与验收标准）")
                for p in procs:
                    steps = [s for s in p.get("steps", []) if isinstance(s, dict)]
                    used = p.get("use_count", 1)
                    lines.append(
                        f"- 🔁 目标：{p.get('goal', '')[:120]}（用过{used}次）"
                    )
                    for j, s in enumerate(steps, 1):
                        title = str(s.get("title", ""))[:80]
                        acc = str(s.get("acceptance", ""))[:60]
                        tail = f" — 验收:{acc}" if acc else ""
                        lines.append(f"    {j}. {title}{tail}")
        except Exception:
            pass

    if not lines:
        return ""

    result = "\n".join(lines)
    # 总长安全封顶（保留开头，因最重要的画像/标题在前）
    max_chars = int(get_config("memory_max_inject_chars", 2500))
    if max_chars > 0 and len(result) > max_chars:
        result = result[:max_chars]
    return result
