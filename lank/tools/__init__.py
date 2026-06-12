"""
工具注册与调度模块
管理所有可用的工具，供 AI 调用
"""

from typing import Any, Callable, Dict, List, Optional, Tuple

# 工具注册表
_tool_registry: Dict[str, Dict[str, Any]] = {}


def register_tool(
    name: str,
    description: str,
    func: Callable,
    parameters: List[Dict[str, Any]],
    requires_approval: bool = False,
) -> None:
    """注册一个工具"""
    _tool_registry[name] = {
        "name": name,
        "description": description,
        "function": func,
        "parameters": parameters,
        "requires_approval": requires_approval,
    }


def get_tool(name: str) -> Optional[Dict[str, Any]]:
    """获取工具信息"""
    return _tool_registry.get(name)


def get_all_tools() -> List[Dict[str, Any]]:
    """获取所有工具信息（用于 API 调用）"""
    tools = []
    for name, info in _tool_registry.items():
        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": info["description"],
                "parameters": {
                    "type": "object",
                    "properties": {
                        p["name"]: {
                            "type": p.get("type", "string"),
                            "description": p.get("description", ""),
                        }
                        for p in info["parameters"]
                    },
                    "required": [p["name"] for p in info["parameters"] if p.get("required", True)],
                },
            },
        })
    return tools


def get_tool_descriptions() -> str:
    """获取工具描述文本（用于系统提示词）"""
    if not _tool_registry:
        return ""
    
    lines = ["\n## 可用工具", ""]
    for name, info in _tool_registry.items():
        lines.append(f"### {name}")
        lines.append(f"描述: {info['description']}")
        if info["parameters"]:
            lines.append("参数:")
            for p in info["parameters"]:
                required = "必填" if p.get("required", True) else "可选"
                lines.append(f"  - {p['name']} ({p.get('type', 'string')}, {required}): {p.get('description', '')}")
        if info["requires_approval"]:
            lines.append("⚠️ 需要用户确认")
        lines.append("")
    
    return "\n".join(lines)


def execute_tool(name: str, arguments: Dict[str, Any]) -> Tuple[bool, str]:
    """执行工具调用
    
    Returns:
        (success, result_message)
    """
    info = get_tool(name)
    if not info:
        return False, f"错误: 未知工具 '{name}'"
    
    try:
        result = info["function"](**arguments)
        return True, str(result)
    except Exception as e:
        return False, f"工具执行错误: {e}"


def needs_approval(name: str) -> bool:
    """检查工具是否需要用户确认"""
    info = get_tool(name)
    return info is not None and info.get("requires_approval", False)


# 导入并注册所有工具
from . import file_ops
from . import cmd_exec
from . import system
from . import todo_tools
