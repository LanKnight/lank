"""
memory/store.py - 记忆持久化层（design.md §8）

数据布局：
  ~/.lank/memory/
  ├── history/           # 原始会话（回溯用）
  ├── summaries.json     # 情景记忆：会话摘要（LLM 生成）
  ├── facts.json         # 语义记忆：事实/偏好（来源/时间/置信度/重要性）
  └── profile.json       # 用户画像（由 facts 聚合，兼容现有）
"""

import json
import os
import re
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import get_config
from ..logs import get_logger
from ..utils import atomic_write_json

logger = get_logger("memory.store")

MEMORY_DIR = Path.home() / ".lank" / "memory"
HISTORY_DIR = MEMORY_DIR / "history"
SUMMARIES_FILE = MEMORY_DIR / "summaries.json"
FACTS_FILE = MEMORY_DIR / "facts.json"
PROFILE_FILE = MEMORY_DIR / "profile.json"
PROCEDURES_FILE = MEMORY_DIR / "procedures.json"   # 程序性记忆：可复用的工作流/步骤模式

# 同进程线程安全（读-改-写路径加锁，防并发丢更新/撞 id）
_store_lock = threading.Lock()


def ensure_memory_dir() -> None:
    """确保记忆目录存在"""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════ 原始会话 ═══════════════

def save_conversation(messages: List[Dict[str, Any]], session_id: Optional[str] = None) -> str:
    """保存对话历史（原子写；会话内建议复用同一 session_id）

    /resume 续写场景：目标文件已存在时合并旧消息（保留更早历史），
    避免"最近 N 条"窗口逐次挤掉头部。
    """
    if not get_config("memory_enabled", True):
        return ""

    ensure_memory_dir()
    if session_id is None:
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{uuid.uuid4().hex[:4]}"

    filepath = HISTORY_DIR / f"{session_id}.json"

    # 合并旧文件中的更早消息（去重：以 role+content 判定）
    merged = list(messages)
    if filepath.exists():
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                old_msgs = json.load(f).get("messages", [])
            seen = {(m.get("role"), m.get("content")) for m in merged}
            merged = list(old_msgs) + [
                m for m in messages
                if (m.get("role"), m.get("content")) not in seen
            ]
        except Exception:
            merged = list(messages)

    data = {
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
        "messages": merged[-200:],  # 窗口 200，兼顾长会话与文件体积
    }
    tmp = filepath.with_name(f"{filepath.name}.{uuid.uuid4().hex[:6]}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, filepath)
    except Exception as e:
        logger.warning("保存会话失败 %s: %s", filepath, e)
    return session_id


def load_conversation(session_id: str) -> Optional[List[Dict[str, Any]]]:
    """加载指定会话的历史消息（校验路径不越界，防 /resume 路径穿越）"""
    if not session_id or "/" in session_id or "\\" in session_id or ".." in session_id:
        return None
    filepath = HISTORY_DIR / f"{session_id}.json"
    try:
        resolved = filepath.resolve()
        if not str(resolved).startswith(str(HISTORY_DIR.resolve())):
            return None
    except OSError:
        return None
    if not filepath.exists():
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("messages", [])
    except Exception:
        return None


def list_sessions(days: int = 7) -> List[Dict[str, Any]]:
    """获取最近的会话元信息列表（按真实时间戳排序，不依赖文件名）"""
    ensure_memory_dir()
    if not HISTORY_DIR.exists():
        return []
    cutoff = datetime.now() - timedelta(days=days)
    conversations = []
    for f in HISTORY_DIR.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            ts = datetime.fromisoformat(data["timestamp"])
            if ts < cutoff:
                continue
            conversations.append({
                "session_id": data["session_id"],
                "timestamp": data["timestamp"],
                "message_count": len(data.get("messages", [])),
            })
        except Exception:
            continue
    conversations.sort(key=lambda c: c["timestamp"], reverse=True)
    return conversations


# ═══════════════ 情景记忆（摘要） ═══════════════

# 进程级 mtime 缓存：避免检索/注入路径反复全量读盘
_summaries_cache: Optional[Dict[str, Any]] = None
_summaries_mtime: Optional[float] = None
_facts_cache: Optional[Dict[str, Any]] = None
_facts_mtime: Optional[float] = None


def _file_mtime(path: Path) -> Optional[float]:
    try:
        return path.stat().st_mtime if path.exists() else None
    except OSError:
        return None


def _load_summaries() -> Dict[str, Any]:
    global _summaries_cache, _summaries_mtime
    mtime = _file_mtime(SUMMARIES_FILE)
    if _summaries_cache is not None and mtime == _summaries_mtime:
        return _summaries_cache
    if SUMMARIES_FILE.exists():
        try:
            with open(SUMMARIES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            _summaries_cache = data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, IOError, AttributeError):
            _summaries_cache = {}
    else:
        _summaries_cache = {}
    _summaries_mtime = mtime
    return _summaries_cache


def add_summary(session_id: str, timestamp: str, summary: str,
                keywords: Optional[List[str]] = None, messages_count: int = 0) -> None:
    """写入会话摘要（加锁防并发丢更新；mtime 变化自动刷新缓存）"""
    with _store_lock:
        data = _load_summaries()
        data[session_id] = {
            "session_id": session_id,
            "timestamp": timestamp,
            "summary": summary,
            "keywords": keywords or [],
            "messages_count": messages_count,
        }
        atomic_write_json(SUMMARIES_FILE, data)


def load_summaries() -> Dict[str, Any]:
    """加载全部会话摘要"""
    return _load_summaries()


# ═══════════════ 语义记忆（事实） ═══════════════

def _load_facts() -> Dict[str, Any]:
    global _facts_cache, _facts_mtime
    mtime = _file_mtime(FACTS_FILE)
    if _facts_cache is not None and mtime == _facts_mtime:
        return _facts_cache
    if FACTS_FILE.exists():
        try:
            with open(FACTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            _facts_cache = data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, IOError, AttributeError):
            _facts_cache = {}
    else:
        _facts_cache = {}
    _facts_mtime = mtime
    return _facts_cache


def _next_fact_id(facts: Dict[str, Any]) -> str:
    """生成下一个事实 id（容错：非法键跳过）"""
    max_n = 0
    for k in facts:
        if "_" in k:
            try:
                max_n = max(max_n, int(k.split("_")[1]))
            except (ValueError, IndexError):
                continue
    return f"fact_{max_n + 1}"


_FACT_WORD_RE = re.compile(r"[a-zA-Z0-9_]+")


def _norm_tokens(text: str) -> set:
    """归一化分词：英文词 + 中文 2-gram（用于近似去重，不依赖外部库）"""
    tokens = set(_FACT_WORD_RE.findall((text or "").lower()))
    cjk = "".join(re.findall(r"[\u4e00-\u9fff]", text or ""))
    if len(cjk) >= 2:
        tokens.update(cjk[i:i + 2] for i in range(len(cjk) - 1))
    return tokens


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def add_fact(text: str, source: str = "auto", importance: int = 1) -> str:
    """写入事实（近似去重：相似度达阈则合并而非新增；加锁防并发撞 id）

    旧版仅按整串相等去重，同义改写会不断堆积。现改为基于词元 Jaccard
    相似度合并：命中则累加提及次数/取更高重要性，显式来源优先保留。
    """
    with _store_lock:
        facts = _load_facts()
        now = datetime.now().isoformat()
        threshold = float(get_config("memory_dedup_similarity", 0.85) or 0.85)
        new_tokens = _norm_tokens(text)

        matched_id: Optional[str] = None
        for fid, f in facts.items():
            if not isinstance(f, dict):
                continue
            old = f.get("text", "").strip()
            if old == text.strip() or _jaccard(new_tokens, _norm_tokens(old)) >= threshold:
                matched_id = fid
                break

        if matched_id is not None:
            f = facts[matched_id]
            f["mention_count"] = f.get("mention_count", 1) + 1
            f["importance"] = max(f.get("importance", 1), importance)
            if source == "explicit" and f.get("source") != "explicit":
                f["source"] = "explicit"
            if len(text) > len(f.get("text", "")):
                f["text"] = text
            f["updated_at"] = now
            atomic_write_json(FACTS_FILE, facts)
            return matched_id

        fid = _next_fact_id(facts)
        facts[fid] = {
            "text": text,
            "source": source,           # auto / explicit
            "importance": importance,   # 1-3
            "mention_count": 1,
            "created_at": now,
            "updated_at": now,
        }
        atomic_write_json(FACTS_FILE, facts)
        return fid


def remove_fact(fact_id: str) -> bool:
    """删除事实（加锁防并发丢更新）"""
    with _store_lock:
        facts = _load_facts()
        if fact_id in facts:
            del facts[fact_id]
            atomic_write_json(FACTS_FILE, facts)
            return True
        return False


def load_facts() -> Dict[str, Any]:
    """加载全部事实"""
    return _load_facts()


# ═══════════════ 用户画像（由事实聚合） ═══════════════

def aggregate_profile() -> Dict[str, Any]:
    """由 facts 聚合生成画像（profile.json 兼容格式）"""
    facts = _load_facts()
    profile: Dict[str, Any] = {}
    for fid, f in facts.items():
        # key 用事实 id，避免同前缀文本互相覆盖
        profile[fid] = {
            "value": f.get("text", ""),
            "updated_at": f.get("updated_at", "")[:10],
            "source": f.get("source", "auto"),
            "importance": f.get("importance", 1),
        }
    return profile


def get_profile() -> Dict[str, Any]:
    """获取用户画像（facts 聚合优先，profile.json 补缺，旧数据不隐身）"""
    profile: Dict[str, Any] = {}
    facts = _load_facts()
    if facts:
        profile.update(aggregate_profile())
    if PROFILE_FILE.exists():
        try:
            with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                legacy = json.load(f)
            if isinstance(legacy, dict):
                profile.update(legacy)
        except Exception:
            pass
    return profile


def get_profile_summary() -> str:
    """用户画像摘要（用于 AI 提示词）"""
    profile = get_profile()
    if not profile:
        return ""
    lines = ["\n## 用户画像", ""]
    for info in profile.values():
        value = info.get("value", "")
        updated = info.get("updated_at", "")[:10]
        source = "💾" if info.get("source") == "explicit" else ""
        lines.append(f"- {source} {value} (记录于 {updated})")
    return "\n".join(lines)


def update_profile(key: str, value: Any) -> None:
    """兼容旧接口：写入画像（同时落一条事实）"""
    add_fact(str(value), source="explicit", importance=2)
    profile = get_profile()
    profile[key] = {
        "value": value,
        "updated_at": datetime.now().isoformat(),
    }
    atomic_write_json(PROFILE_FILE, profile)


# ═══════════════ 程序性记忆（可复用流程） ═══════════════
# design.md 规划的第四层：任务成功后沉淀“目标→有序步骤”的模式，
# 供以后同类任务规划时复用。纯本地读写，不依赖 LLM。

_procs_cache: Optional[Dict[str, Any]] = None
_procs_mtime: Optional[float] = None


def _load_procedures() -> Dict[str, Any]:
    global _procs_cache, _procs_mtime
    mtime = _file_mtime(PROCEDURES_FILE)
    if _procs_cache is not None and mtime == _procs_mtime:
        return _procs_cache
    if PROCEDURES_FILE.exists():
        try:
            with open(PROCEDURES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            _procs_cache = data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, IOError, AttributeError):
            _procs_cache = {}
    else:
        _procs_cache = {}
    _procs_mtime = mtime
    return _procs_cache


def _next_proc_id(procs: Dict[str, Any]) -> str:
    max_n = 0
    for k in procs:
        if "_" in k:
            try:
                max_n = max(max_n, int(k.split("_")[1]))
            except (ValueError, IndexError):
                continue
    return f"proc_{max_n + 1}"


def add_procedure(goal: str, steps: List[Dict[str, Any]],
                  keywords: Optional[List[str]] = None,
                  review_criteria: str = "", max_steps: int = 10) -> str:
    """沉淀一条可复用流程（目标近似重复则合并、累加复用次数）"""
    if not goal or not goal.strip() or not steps:
        return ""
    with _store_lock:
        procs = _load_procedures()
        now = datetime.now().isoformat()
        gtokens = _norm_tokens(goal)
        for pid, p in procs.items():
            if isinstance(p, dict) and _jaccard(gtokens, _norm_tokens(p.get("goal", ""))) >= 0.9:
                p["use_count"] = int(p.get("use_count", 1)) + 1
                p["updated_at"] = now
                atomic_write_json(PROCEDURES_FILE, procs)
                return pid
        clean_steps: List[Dict[str, str]] = []
        for s in steps[:max_steps]:
            if not isinstance(s, dict):
                continue
            clean_steps.append({
                "title": str(s.get("title", ""))[:200],
                "action": str(s.get("action", ""))[:200],
                "acceptance": str(s.get("acceptance", ""))[:160],
            })
        if not clean_steps:
            return ""
        pid = _next_proc_id(procs)
        procs[pid] = {
            "goal": goal.strip()[:300],
            "steps": clean_steps,
            "keywords": keywords or [],
            "review_criteria": (review_criteria or "")[:200],
            "created_at": now,
            "updated_at": now,
            "use_count": 1,
            "success_count": 1,
        }
        atomic_write_json(PROCEDURES_FILE, procs)
        return pid


def load_procedures() -> Dict[str, Any]:
    """加载全部程序性记忆"""
    return _load_procedures()


def remove_procedure(proc_id: str) -> bool:
    with _store_lock:
        procs = _load_procedures()
        if proc_id in procs:
            del procs[proc_id]
            atomic_write_json(PROCEDURES_FILE, procs)
            return True
        return False


# ═══════════════ 记忆导入 / 导出（迁移与备份） ═══════════════


def export_memories(path: Optional[str] = None) -> str:
    """将长期事实/会话摘要/可复用流程导出为单个 JSON，返回落盘路径。

    不传 path 则写入 MEMORY_DIR 下带时间戳的文件；导出为快照，便于迁移/备份。
    """
    data = {
        "version": 1,
        "exported_at": datetime.now().isoformat(),
        "facts": load_facts(),
        "summaries": load_summaries(),
        "procedures": load_procedures(),
    }
    if path:
        out = Path(path)
    else:
        out = MEMORY_DIR / f"memory_export_{datetime.now():%Y%m%d_%H%M%S}.json"
    atomic_write_json(out, data)
    return str(out)


def import_memories(path: str, mode: str = "merge") -> Dict[str, int]:
    """从导出 JSON 导入记忆，返回各类别导入计数。

    mode="merge"（默认）：逐条走 add_* 合并，事实/流程自然近似去重；摘要按 session_id 不覆盖。
    mode="overwrite"：先清空本地事实与流程再导入快照；摘要按 session_id 覆盖。
    失败（文件不存在/非法 JSON）时返回带 error 的零计数，绝不抛异常中断主流程。
    """
    global _facts_cache, _facts_mtime, _procs_cache, _procs_mtime
    counts = {"facts": 0, "procedures": 0, "summaries": 0, "error": 0}
    p = Path(path)
    if not p.exists():
        counts["error"] = 1
        return counts
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError, UnicodeDecodeError):
        counts["error"] = 1
        return counts
    if not isinstance(data, dict):
        counts["error"] = 1
        return counts

    if mode == "overwrite":
        # 先置空事实/流程（加锁写空 + 同步失效缓存），再用快照回灌
        with _store_lock:
            atomic_write_json(FACTS_FILE, {})
            _facts_cache = {}
            _facts_mtime = _file_mtime(FACTS_FILE)
            atomic_write_json(PROCEDURES_FILE, {})
            _procs_cache = {}
            _procs_mtime = _file_mtime(PROCEDURES_FILE)

    for _k, f in (data.get("facts") or {}).items():
        if isinstance(f, dict) and f.get("text"):
            add_fact(
                str(f["text"]),
                source=str(f.get("source", "auto")),
                importance=int(f.get("importance", 1) or 1),
            )
            counts["facts"] += 1

    for _k, pr in (data.get("procedures") or {}).items():
        if isinstance(pr, dict) and pr.get("goal") and pr.get("steps"):
            add_procedure(
                str(pr["goal"]),
                list(pr["steps"]),
                keywords=list(pr.get("keywords", []) or []),
                review_criteria=str(pr.get("review_criteria", "")),
            )
            counts["procedures"] += 1

    existing = load_summaries()
    for sid, s in (data.get("summaries") or {}).items():
        if not isinstance(s, dict) or not s.get("summary"):
            continue
        if mode != "overwrite" and sid in existing:
            continue
        add_summary(
            sid,
            str(s.get("timestamp", "")),
            str(s.get("summary", "")),
            list(s.get("keywords", []) or []),
            int(s.get("messages_count", s.get("message_count", 0)) or 0),
        )
        counts["summaries"] += 1

    return counts
