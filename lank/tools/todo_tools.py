"""
待办事项管理工具
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from . import register_tool

TODO_FILE = Path.home() / ".lank" / "todos.json"


def _load_todos() -> List[Dict[str, Any]]:
    """加载待办事项"""
    if TODO_FILE.exists():
        try:
            with open(TODO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def _save_todos(todos: List[Dict[str, Any]]) -> None:
    """保存待办事项"""
    TODO_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TODO_FILE, "w", encoding="utf-8") as f:
        json.dump(todos, f, ensure_ascii=False, indent=2)


def todo_add(task: str, priority: str = "medium") -> str:
    """添加待办事项
    
    Args:
        task: 任务描述
        priority: 优先级 (high/medium/low)
    
    Returns:
        操作结果
    """
    todos = _load_todos()
    todo = {
        "id": len(todos) + 1,
        "task": task,
        "priority": priority,
        "done": False,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    todos.append(todo)
    _save_todos(todos)
    return f"✅ 已添加待办 [#{todo['id']}]: {task}"


def todo_list(status: str = "all") -> str:
    """列出待办事项
    
    Args:
        status: 筛选状态 - "all"(全部), "pending"(未完成), "done"(已完成)
    
    Returns:
        待办列表
    """
    todos = _load_todos()
    
    if not todos:
        return "📋 暂无待办事项"
    
    if status == "pending":
        todos = [t for t in todos if not t["done"]]
    elif status == "done":
        todos = [t for t in todos if t["done"]]
    
    if not todos:
        return f"📋 没有{status}状态的待办事项"
    
    lines = ["📋 待办事项列表", "=" * 40]
    for t in todos:
        status_icon = "✅" if t["done"] else "⬜"
        priority_map = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        priority_icon = priority_map.get(t["priority"], "🟡")
        lines.append(f"  {status_icon} [#{t['id']}] {priority_icon} {t['task']}")
        lines.append(f"      创建: {t['created_at']}")
    
    return "\n".join(lines)


def todo_done(todo_id: int) -> str:
    """标记待办为已完成
    
    Args:
        todo_id: 待办事项 ID
    
    Returns:
        操作结果
    """
    todos = _load_todos()
    for t in todos:
        if t["id"] == todo_id:
            t["done"] = True
            t["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            _save_todos(todos)
            return f"✅ 已完成: {t['task']}"
    return f"❌ 未找到待办 #{todo_id}"


def todo_delete(todo_id: int) -> str:
    """删除待办事项
    
    Args:
        todo_id: 待办事项 ID
    
    Returns:
        操作结果
    """
    todos = _load_todos()
    for i, t in enumerate(todos):
        if t["id"] == todo_id:
            deleted = todos.pop(i)
            _save_todos(todos)
            return f"🗑️ 已删除: {deleted['task']}"
    return f"❌ 未找到待办 #{todo_id}"


# 注册工具
register_tool(
    name="todo_add",
    description="添加待办事项",
    func=todo_add,
    parameters=[
        {"name": "task", "type": "string", "description": "任务描述"},
        {"name": "priority", "type": "string", "description": "优先级: high/medium/low", "required": False},
    ],
)

register_tool(
    name="todo_list",
    description="列出待办事项",
    func=todo_list,
    parameters=[
        {"name": "status", "type": "string", "description": "筛选: all/pending/done", "required": False},
    ],
)

register_tool(
    name="todo_done",
    description="标记待办事项为已完成",
    func=todo_done,
    parameters=[
        {"name": "todo_id", "type": "integer", "description": "待办事项 ID"},
    ],
)

register_tool(
    name="todo_delete",
    description="删除待办事项",
    func=todo_delete,
    parameters=[
        {"name": "todo_id", "type": "integer", "description": "待办事项 ID"},
    ],
)
