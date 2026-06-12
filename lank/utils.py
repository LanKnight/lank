"""
工具函数模块 - 主题、统计、导出等创意功能
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import get_config

STATS_FILE = Path.home() / ".lank" / "stats.json"


# ===== 主题系统 =====

THEMES = {
    "default": {
        "name": "默认",
        "primary": "bright_cyan",
        "secondary": "magenta",
        "accent": "yellow",
        "success": "green",
        "error": "red",
        "panel_border": "bright_cyan",
        "user_color": "cyan",
        "ai_color": "magenta",
        "system_color": "green",
    },
    "dark": {
        "name": "暗色",
        "primary": "blue",
        "secondary": "purple",
        "accent": "gold",
        "success": "green",
        "error": "red",
        "panel_border": "blue",
        "user_color": "light_cyan",
        "ai_color": "light_magenta",
        "system_color": "light_green",
    },
    "cyberpunk": {
        "name": "赛博朋克",
        "primary": "bright_magenta",
        "secondary": "bright_cyan",
        "accent": "bright_yellow",
        "success": "bright_green",
        "error": "bright_red",
        "panel_border": "bright_magenta",
        "user_color": "bright_cyan",
        "ai_color": "bright_magenta",
        "system_color": "bright_green",
    },
    "hacker": {
        "name": "黑客",
        "primary": "green",
        "secondary": "bright_green",
        "accent": "yellow",
        "success": "green",
        "error": "red",
        "panel_border": "green",
        "user_color": "bright_green",
        "ai_color": "green",
        "system_color": "dark_green",
    },
    "sunset": {
        "name": "日落",
        "primary": "orange1",
        "secondary": "hot_pink",
        "accent": "gold1",
        "success": "green",
        "error": "red",
        "panel_border": "orange1",
        "user_color": "orange1",
        "ai_color": "hot_pink",
        "system_color": "light_sky_blue",
    },
}


def get_theme() -> Dict[str, str]:
    """获取当前主题配置"""
    theme_name = get_config("theme", "default")
    return THEMES.get(theme_name, THEMES["default"])


def list_themes() -> str:
    """列出所有可用主题"""
    lines = ["🎨 可用主题:", ""]
    current = get_config("theme", "default")
    for key, theme in THEMES.items():
        marker = " ✅" if key == current else ""
        lines.append(f"  {key:15s} - {theme['name']}{marker}")
    return "\n".join(lines)


# ===== 使用统计 =====

def _load_stats() -> Dict[str, Any]:
    """加载统计数据"""
    if STATS_FILE.exists():
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {
        "first_use": datetime.now().isoformat(),
        "total_sessions": 0,
        "total_messages": 0,
        "total_tool_calls": 0,
        "daily_stats": {},
    }


def _save_stats(stats: Dict[str, Any]) -> None:
    """保存统计数据"""
    STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def record_session(messages_count: int, tool_calls: int = 0) -> None:
    """记录一次会话"""
    stats = _load_stats()
    stats["total_sessions"] = stats.get("total_sessions", 0) + 1
    stats["total_messages"] = stats.get("total_messages", 0) + messages_count
    stats["total_tool_calls"] = stats.get("total_tool_calls", 0) + tool_calls
    
    today = datetime.now().strftime("%Y-%m-%d")
    if today not in stats.get("daily_stats", {}):
        stats.setdefault("daily_stats", {})[today] = {
            "sessions": 0,
            "messages": 0,
            "tool_calls": 0,
        }
    stats["daily_stats"][today]["sessions"] += 1
    stats["daily_stats"][today]["messages"] += messages_count
    stats["daily_stats"][today]["tool_calls"] += tool_calls
    
    _save_stats(stats)


def get_stats_summary() -> str:
    """获取统计摘要"""
    stats = _load_stats()
    
    first_use = stats.get("first_use", "")[:10]
    total_sessions = stats.get("total_sessions", 0)
    total_messages = stats.get("total_messages", 0)
    total_tool_calls = stats.get("total_tool_calls", 0)
    
    lines = [
        "📊 使用统计",
        "=" * 40,
        f"首次使用: {first_use}",
        f"总会话数: {total_sessions}",
        f"总消息数: {total_messages}",
        f"工具调用: {total_tool_calls}",
        "",
    ]
    
    # 最近 7 天统计
    daily = stats.get("daily_stats", {})
    recent_days = sorted(daily.keys(), reverse=True)[:7]
    if recent_days:
        lines.append("最近 7 天:")
        for day in recent_days:
            d = daily[day]
            lines.append(f"  {day}: {d['sessions']} 会话, {d['messages']} 消息, {d['tool_calls']} 工具调用")
    
    return "\n".join(lines)


# ===== 导出功能 =====

def export_conversation(messages: List[Dict[str, Any]], format: str = "markdown") -> Optional[str]:
    """导出对话
    
    Args:
        messages: 对话消息列表
        format: 导出格式 (markdown/json)
    
    Returns:
        导出文件路径，失败返回 None
    """
    if not messages:
        return None
    
    export_dir = Path.home() / ".lank" / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if format == "json":
        filepath = export_dir / f"conversation_{timestamp}.json"
        data = {
            "exported_at": datetime.now().isoformat(),
            "messages": messages,
        }
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return str(filepath)
        except Exception:
            return None
    
    else:  # markdown
        filepath = export_dir / f"conversation_{timestamp}.md"
        lines = [
            "# LANK 对话导出",
            f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"消息数: {len(messages)}",
            "",
            "---",
            "",
        ]
        
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            
            if role == "user":
                lines.append(f"### 👤 用户\n\n{content}\n")
            elif role == "assistant":
                lines.append(f"### 🤖 AI\n\n{content}\n")
            elif role == "system":
                lines.append(f"> ⚙️ {content}\n")
            elif role == "tool":
                lines.append(f"> 🔧 工具结果: {content[:200]}\n")
        
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            return str(filepath)
        except Exception:
            return None


# ===== 版本检查 =====

def check_for_updates() -> str:
    """检查更新（简单实现）"""
    try:
        import urllib.request
        import json as json_module
        
        url = "https://api.github.com/repos/LanKnight/lank/releases/latest"
        req = urllib.request.Request(url, headers={"User-Agent": "lank"})
        
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json_module.loads(response.read().decode())
            latest_version = data.get("tag_name", "").lstrip("v")
            
            from . import __version__
            current_version = __version__
            
            if latest_version and latest_version > current_version:
                return f"📢 发现新版本: v{latest_version} (当前: v{current_version})\n   请执行: pip install --upgrade lank"
            else:
                return f"✅ 当前已是最新版本: v{current_version}"
    except Exception:
        return "⚠️ 无法检查更新（请检查网络连接）"
