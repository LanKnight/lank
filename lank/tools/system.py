"""
系统工具 - 日期时间、系统信息查询等
"""

import datetime
import os
import platform
import sys

from . import register_tool


def get_datetime(format_str: str = "full") -> str:
    """获取当前日期和时间
    
    Args:
        format_str: 格式 - "full"(完整), "date"(仅日期), "time"(仅时间), "timestamp"(时间戳)
    
    Returns:
        日期时间字符串
    """
    now = datetime.datetime.now()
    
    if format_str == "date":
        return now.strftime("%Y-%m-%d")
    elif format_str == "time":
        return now.strftime("%H:%M:%S")
    elif format_str == "timestamp":
        return str(now.timestamp())
    else:
        return now.strftime("%Y-%m-%d %H:%M:%S")


def get_system_info() -> str:
    """获取系统信息"""
    info = [
        f"系统: {platform.system()} {platform.release()}",
        f"主机名: {platform.node()}",
        f"Python: {sys.version}",
        f"当前目录: {os.getcwd()}",
        f"用户: {os.getenv('USERNAME') or os.getenv('USER') or 'unknown'}",
    ]
    
    # 磁盘使用情况（仅 Windows）
    if sys.platform == "win32":
        try:
            import ctypes
            free_bytes = ctypes.c_ulonglong(0)
            total_bytes = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                ctypes.c_wchar_p(os.getcwd().split(":")[0] + ":\\"),
                None, ctypes.pointer(total_bytes), ctypes.pointer(free_bytes)
            )
            total_gb = total_bytes.value / (1024**3)
            free_gb = free_bytes.value / (1024**3)
            used_gb = total_gb - free_gb
            info.append(f"磁盘: 总计 {total_gb:.1f}GB, 已用 {used_gb:.1f}GB, 剩余 {free_gb:.1f}GB")
        except Exception:
            pass
    
    return "\n".join(info)


def calculate(expression: str) -> str:
    """计算数学表达式
    
    Args:
        expression: 数学表达式（如 "1 + 2 * 3"）
    
    Returns:
        计算结果
    """
    # 安全计算 - 只允许基本数学运算
    allowed_chars = set("0123456789.+-*/()% ")
    for c in expression:
        if c not in allowed_chars:
            return f"错误: 表达式包含不允许的字符: '{c}'"
    
    try:
        result = eval(expression, {"__builtins__": {}}, {})
        return f"{expression} = {result}"
    except ZeroDivisionError:
        return "错误: 除以零"
    except Exception as e:
        return f"计算错误: {e}"


# 注册工具
register_tool(
    name="get_datetime",
    description="获取当前日期和时间",
    func=get_datetime,
    parameters=[
        {"name": "format_str", "type": "string", "description": "格式: full/date/time/timestamp", "required": False},
    ],
)

register_tool(
    name="get_system_info",
    description="获取系统信息（操作系统、Python版本、磁盘等）",
    func=get_system_info,
    parameters=[],
)

register_tool(
    name="calculate",
    description="计算数学表达式",
    func=calculate,
    parameters=[
        {"name": "expression", "type": "string", "description": "数学表达式"},
    ],
)
