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
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import get_config
from ..utils import atomic_write_json

MEMORY_DIR = Path.home() / ".lank" / "memory"
HISTORY_DIR = MEMORY_DIR / "history"
SUMMARIES_FILE = MEMORY_DIR / "summaries.json"
FACTS_FILE = MEMORY_DIR / "facts.json"
PROFILE_FILE = MEMORY_DIR / "profile.json"


def ensure_memory_dir() -> None:
    """确保记忆目录存在"""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════ 原始会话 ═══════════════

def save_conversation(messages: List[Dict[str, Any]], session_id: Optional[str] = None) -> str:
    """保存对话历史（原子写；会话内建议复用同一 session_id）"""
    if not get_config("memory_enabled", True):
        return ""

    ensure_memory_dir()
    if session_id is None:
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{uuid.uuid4().hex[:4]}"

    filepath = HISTORY_DIR / f"{session_id}.json"
    data = {
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
        "messages": messages[-50:],  # 只保存最近 50 条
    }
    tmp = filepath.with_suffix(".json.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, filepath)
    except Exception:
        pass
    return session_id


def load_conversation(session_id: str) -> Optional[List[Dict[str, Any]]]:
    """加载指定会话的历史消息"""
    filepath = HISTORY_DIR / f"{session_id}.json"
    if not filepath.exists():
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("messages", [])
    except Exception:
        return None


def list_sessions(days: int = 7) -> List[Dict[str, Any]]:
    """获取最近的会话元信息列表"""
    ensure_memory_dir()
    if not HISTORY_DIR.exists():
        return []
    cutoff = datetime.now() - timedelta(days=days)
    conversations = []
    for f in sorted(HISTORY_DIR.glob("*.json"), reverse=True):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            ts = datetime.fromisoformat(data["timestamp"])
            if ts < cutoff:
                break
            conversations.append({
                "session_id": data["session_id"],
                "timestamp": data["timestamp"],
                "message_count": len(data.get("messages", [])),
            })
        except Exception:
            continue
    return conversations


# ═══════════════ 情景记忆（摘要） ═══════════════

def _load_summaries() -> Dict[str, Any]:
    if SUMMARIES_FILE.exists():
        try:
            with open(SUMMARIES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def add_summary(session_id: str, timestamp: str, summary: str,
                keywords: Optional[List[str]] = None, messages_count: int = 0) -> None:
    """写入会话摘要"""
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
    if FACTS_FILE.exists():
        try:
            with open(FACTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _next_fact_id(facts: Dict[str, Any]) -> str:
    n = max((int(k.split("_")[1]) for k in facts if "_" in k), default=0) + 1
    return f"fact_{n}"


def add_fact(text: str, source: str = "auto", importance: int = 1) -> str:
    """写入事实（同文本合并，更新提及次数）"""
    facts = _load_facts()
    now = datetime.now().isoformat()
    for fid, f in facts.items():
        if f.get("text", "").strip() == text.strip():
            f["mention_count"] = f.get("mention_count", 1) + 1
            f["importance"] = max(f.get("importance", 1), importance)
            f["updated_at"] = now
            atomic_write_json(FACTS_FILE, facts)
            return fid
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
    """删除事实"""
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
    for f in facts.values():
        text = f.get("text", "")
        key = text[:20]
        profile[key] = {
            "value": text,
            "updated_at": f.get("updated_at", "")[:10],
            "source": f.get("source", "auto"),
            "importance": f.get("importance", 1),
        }
    return profile


def get_profile() -> Dict[str, Any]:
    """获取用户画像（facts 优先，兼容旧 profile.json）"""
    facts = _load_facts()
    if facts:
        return aggregate_profile()
    if PROFILE_FILE.exists():
        try:
            with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


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
