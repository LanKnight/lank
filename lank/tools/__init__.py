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

def _check_type(pname: str, ptype: str, value: Any) -> Optional[str]:
    """类型检查（bool 不能冒充 int/number）"""
    if value is None:
        return None
    if ptype == "string":
        if not isinstance(value, str):
            return f"参数 {pname} 类型错误: 期望 string, 实际 {type(value).__name__}"
    elif ptype == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            return f"参数 {pname} 类型错误: 期望 integer, 实际 {type(value).__name__}"
    elif ptype == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"参数 {pname} 类型错误: 期望 number, 实际 {type(value).__name__}"
    elif ptype == "boolean":
        if not isinstance(value, bool):
            return f"参数 {pname} 类型错误: 期望 boolean, 实际 {type(value).__name__}"
    elif ptype == "array":
        if not isinstance(value, list):
            return f"参数 {pname} 类型错误: 期望 array, 实际 {type(value).__name__}"
    elif ptype == "object":
        if not isinstance(value, dict):
            return f"参数 {pname} 类型错误: 期望 object, 实际 {type(value).__name__}"
    return None


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

        err = _check_type(pname, ptype, arguments[pname])
        if err:
            return err
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
    """检查工具是否需要用户确认（考虑白名单，兼容旧接口）"""
    return needs_confirmation(name, "")


def needs_confirmation(name: str, arg_hint: str = "") -> bool:
    """检查工具调用是否需要用户确认（白名单命中则免确认）

    Args:
        name: 工具名
        arg_hint: 参数提示（execute_command 传命令文本，用于命令白名单匹配）
    """
    info = get_tool(name)
    if info is None:
        return False
    approval = info.get("approval", "none")
    if approval == "none":
        return False
    # 任何需要确认的工具，命中白名单（工具名或命令前缀）则免确认
    if _is_allowlisted(name, arg_hint):
        return False
    return True


# ── 白名单（~/.lank/allowlist.json） ──

def _load_allowlist() -> Dict[str, Any]:
    """加载白名单（损坏/顶层非 dict 时返回空）"""
    if ALLOWLIST_FILE.exists():
        try:
            with open(ALLOWLIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, IOError, AttributeError):
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


def _prefix_match(pattern: str, hint: str) -> bool:
    """命令前缀匹配（词边界：放行 'git status' 不放行 'git statusx'）"""
    import re
    if not pattern:
        return False
    return re.match(r"^{}(\s|$)".format(re.escape(pattern)), hint) is not None


def _is_allowlisted(name: str, arg_hint: str = "") -> bool:
    """判断工具调用是否命中白名单"""
    data = _load_allowlist()
    hint = arg_hint.lower()
    # execute_command 只走命令前缀白名单——tools 列表里的同名条目不生效，
    # 防止空 hint 时把整个命令执行放行
    if name != "execute_command":
        tools = data.get("tools", [])
        if name in tools:
            return True
    commands = data.get("commands", [])
    for entry in commands:
        pattern = (entry.get("pattern") or "").lower()
        if _prefix_match(pattern, hint):
            return True
    # 配置项 cmd_allowlist 同样作为命令前缀白名单生效
    if name == "execute_command":
        cfg_list = get_config("cmd_allowlist", []) or []
        for pat in cfg_list:
            if _prefix_match(str(pat).lower(), hint):
                return True
    return False


def check_allowlist(name: str, arg_hint: str = "") -> bool:
    """对外查询白名单（供确认流程使用）"""
    return _is_allowlisted(name, arg_hint)


def allow_forever(name: str, arg_hint: str = "") -> str:
    """将工具/命令加入永久白名单（execute_command 要求非空命令前缀）"""
    if name == "execute_command":
        if not arg_hint or not arg_hint.strip():
            return "错误: 无法将空命令加入白名单"
        data = _load_allowlist()
        commands = data.setdefault("commands", [])
        if not any(c.get("pattern", "").lower() == arg_hint.lower() for c in commands):
            commands.append({"pattern": arg_hint})
        _save_allowlist(data)
        return f"已加入命令白名单: {arg_hint}"

    data = _load_allowlist()
    tools = data.setdefault("tools", [])
    if name not in tools:
        tools.append(name)
    _save_allowlist(data)
    return f"已加入工具白名单: {name}"


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
