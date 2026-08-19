"""
工具注册与调度模块
管理所有可用的工具，供 AI 调用

工具元数据（v2）：
  - category:      工具分类（file / command / system / todo / plan / question / memory）
  - danger_level:  危险等级（0=只读 1=写文件 2=破坏性 3=执行命令）
  - approval:      确认策略（"none" 自动 / "confirm" 询问 / "whitelist" 白名单免确认）
"""

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..config import get_config
from ..logs import get_logger

logger = get_logger("tools")

# 工具注册表
_tool_registry: Dict[str, Dict[str, Any]] = {}

# 白名单文件 ~/.lank/allowlist.json
ALLOWLIST_FILE = Path.home() / ".lank" / "allowlist.json"

_TYPE_CHECKERS = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
}


def register_tool(
    name: str,
    description: str,
    func: Callable,
    parameters: List[Dict[str, Any]],
    requires_approval: bool = False,
    category: str = "misc",
    danger_level: int = 0,
    approval: str = "",
) -> None:
    """注册一个工具

    Args:
        name: 工具名
        description: 工具描述
        func: 工具函数
        parameters: 参数 schema（name/type/description/required）
        requires_approval: 是否需用户确认（旧字段，兼容）
        category: 工具分类
        danger_level: 危险等级 0-3
        approval: 确认策略 none/confirm/whitelist；缺省由 requires_approval 推导
    """
    if not approval:
        approval = "confirm" if requires_approval else "none"
    _tool_registry[name] = {
        "name": name,
        "description": description,
        "function": func,
        "parameters": parameters,
        "requires_approval": requires_approval,
        "category": category,
        "danger_level": danger_level,
        "approval": approval,
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
        if info["approval"] != "none":
            lines.append("⚠️ 需要用户确认")
        lines.append("")

    return "\n".join(lines)


def _validate_arguments(info: Dict[str, Any], arguments: Dict[str, Any]) -> Optional[str]:
    """轻量参数校验：必填 + 类型。返回错误信息或 None"""
    for p in info["parameters"]:
        pname = p["name"]
        ptype = p.get("type", "string")
        required = p.get("required", True)

        if pname not in arguments:
            if required:
                return f"缺少必填参数: {pname}"
            continue

        value = arguments[pname]
        checker = _TYPE_CHECKERS.get(ptype)
        if checker is not None and value is not None and not isinstance(value, checker):
            return f"参数 {pname} 类型错误: 期望 {ptype}, 实际 {type(value).__name__}"
    return None


def _truncate_result(result: str, limit: Optional[int] = None) -> str:
    """工具结果截断（防止上下文爆炸）"""
    if limit is None:
        limit = int(get_config("tool_output_limit", 8192))
    if len(result) > limit:
        return result[:limit] + f"\n... [已截断，共 {len(result)} 字符]"
    return result


def execute_tool(name: str, arguments: Dict[str, Any]) -> Tuple[bool, str]:
    """执行工具调用

    Returns:
        (success, result_message)
    """
    info = get_tool(name)
    if not info:
        return False, f"错误: 未知工具 '{name}'"

    err = _validate_arguments(info, arguments)
    if err:
        logger.warning("工具 %s 参数校验失败: %s", name, err)
        return False, f"错误: {err}"

    try:
        result = info["function"](**arguments)
        text = str(result)
        logger.info("工具调用: %s args=%s", name, json.dumps(arguments, ensure_ascii=False)[:300])
        return True, _truncate_result(text)
    except Exception as e:
        logger.exception("工具 %s 执行异常", name)
        return False, f"工具执行错误: {e}"


def needs_approval(name: str) -> bool:
    """检查工具是否需要用户确认（考虑白名单）"""
    info = get_tool(name)
    if info is None:
        return False
    approval = info.get("approval", "none")
    if approval == "none":
        return False
    if approval == "whitelist":
        if _is_allowlisted(name, ""):
            return False
        return True
    return True


# ── 白名单（~/.lank/allowlist.json） ──

def _load_allowlist() -> Dict[str, Any]:
    """加载白名单"""
    if ALLOWLIST_FILE.exists():
        try:
            with open(ALLOWLIST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save_allowlist(data: Dict[str, Any]) -> None:
    """保存白名单（原子写）"""
    ALLOWLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = ALLOWLIST_FILE.with_suffix(".json.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, ALLOWLIST_FILE)
    except Exception as e:
        logger.error("保存白名单失败: %s", e)


def _is_allowlisted(name: str, arg_hint: str = "") -> bool:
    """判断工具调用是否命中白名单"""
    data = _load_allowlist()
    tools = data.get("tools", [])
    if name in tools:
        return True
    commands = data.get("commands", [])
    hint = arg_hint.lower()
    for entry in commands:
        pattern = (entry.get("pattern") or "").lower()
        if pattern and hint.startswith(pattern):
            return True
    return False


def check_allowlist(name: str, arg_hint: str = "") -> bool:
    """对外查询白名单（供确认流程使用）"""
    return _is_allowlisted(name, arg_hint)


def allow_forever(name: str, arg_hint: str = "") -> None:
    """将工具/命令加入永久白名单"""
    data = _load_allowlist()
    if name in ("execute_command",) and arg_hint:
        commands = data.setdefault("commands", [])
        if not any(c.get("pattern", "").lower() == arg_hint.lower() for c in commands):
            commands.append({"pattern": arg_hint})
    else:
        tools = data.setdefault("tools", [])
        if name not in tools:
            tools.append(name)
    _save_allowlist(data)


def remove_allowlist(name: str) -> None:
    """从白名单移除"""
    data = _load_allowlist()
    data["tools"] = [t for t in data.get("tools", []) if t != name]
    _save_allowlist(data)


# 导入并注册所有工具
from . import file_ops
from . import cmd_exec
from . import system
from . import todo_tools
from . import plan_tools
from . import memory_tools
