"""
个性化记忆模块
记录对话历史、用户偏好，实现跨会话记忆
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import get_config

MEMORY_DIR = Path.home() / ".lank" / "memory"
HISTORY_DIR = MEMORY_DIR / "history"
PROFILE_FILE = MEMORY_DIR / "profile.json"


def ensure_memory_dir() -> None:
    """确保记忆目录存在"""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def save_conversation(messages: List[Dict[str, Any]], session_id: Optional[str] = None) -> str:
    """保存对话历史
    
    Args:
        messages: 对话消息列表
        session_id: 会话 ID（可选，自动生成）
    
    Returns:
        会话 ID
    """
    if not get_config("memory_enabled", True):
        return ""
    
    ensure_memory_dir()
    
    if session_id is None:
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    filepath = HISTORY_DIR / f"{session_id}.json"
    
    data = {
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
        "messages": messages[-50:],  # 只保存最近 50 条
    }
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
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


def get_recent_conversations(days: int = 7) -> List[Dict[str, Any]]:
    """获取最近的对话列表
    
    Args:
        days: 最近几天
    
    Returns:
        对话摘要列表
    """
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
            
            msgs = data.get("messages", [])
            # 提取摘要
            summary = ""
            for m in msgs:
                if m.get("role") == "user":
                    content = m.get("content", "")
                    if content:
                        summary = content[:50]
                        break
            
            conversations.append({
                "session_id": data["session_id"],
                "timestamp": data["timestamp"],
                "message_count": len(msgs),
                "summary": summary,
            })
        except Exception:
            continue
    
    return conversations


def get_recent_context(max_sessions: int = 3) -> str:
    """获取最近的对话上下文（用于 AI 提示词）
    
    Args:
        max_sessions: 最多加载几个最近的会话
    
    Returns:
        格式化的上下文文本
    """
    ensure_memory_dir()
    if not HISTORY_DIR.exists():
        return ""
    
    sessions = []
    for f in sorted(HISTORY_DIR.glob("*.json"), reverse=True)[:max_sessions]:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            sessions.append(data)
        except Exception:
            continue
    
    if not sessions:
        return ""
    
    lines = ["\n## 历史对话记忆", ""]
    
    for session in sessions:
        ts = session.get("timestamp", "")[:16]
        msgs = session.get("messages", [])
        lines.append(f"--- 会话 {ts} ({len(msgs)} 条消息) ---")
        
        for m in msgs[-6:]:  # 只取最后 6 条
            role = m.get("role", "")
            content = m.get("content", "")
            if role in ("user", "assistant") and content:
                role_name = "用户" if role == "user" else "AI"
                # 截断过长内容
                if len(content) > 100:
                    content = content[:100] + "..."
                lines.append(f"  {role_name}: {content}")
        lines.append("")
    
    return "\n".join(lines)


def update_profile(key: str, value: Any) -> None:
    """更新用户画像信息"""
    ensure_memory_dir()
    
    profile = {}
    if PROFILE_FILE.exists():
        try:
            with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                profile = json.load(f)
        except Exception:
            profile = {}
    
    profile[key] = {
        "value": value,
        "updated_at": datetime.now().isoformat(),
    }
    
    try:
        with open(PROFILE_FILE, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_profile() -> Dict[str, Any]:
    """获取用户画像"""
    if PROFILE_FILE.exists():
        try:
            with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def get_profile_summary() -> str:
    """获取用户画像摘要（用于 AI 提示词）"""
    profile = get_profile()
    if not profile:
        return ""
    
    lines = ["\n## 用户画像", ""]
    for key, info in profile.items():
        value = info.get("value", "")
        updated = info.get("updated_at", "")[:10]
        lines.append(f"- {key}: {value} (记录于 {updated})")
    
    return "\n".join(lines)


def cleanup_old_memories(max_days: int = 30) -> int:
    """清理旧记忆
    
    Args:
        max_days: 保留最近多少天的记忆
    
    Returns:
        清理的文件数
    """
    ensure_memory_dir()
    if not HISTORY_DIR.exists():
        return 0
    
    cutoff = datetime.now() - timedelta(days=max_days)
    cleaned = 0
    
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
    
    return cleaned
