"""
命令执行工具 - 运行 CLI 命令（安全重构版）
类似 Claude 的命令执行能力

安全设计（design.md §7.2）：
  - 危险命令黑名单：命中即拒绝，不询问
  - 输出截断：防止上下文爆炸
  - 工作目录统一使用 working_dir 配置
  - 超时可配置
"""

import os
import re
import shlex
import subprocess
import sys
from typing import List, Optional

from ..config import get_working_dir, get_config
from ..logs import get_logger
from . import register_tool

logger = get_logger("cmd_exec")

# ── 危险命令黑名单（正则，命中即拦截） ──
DANGEROUS_PATTERNS: List[str] = [
    # 删除类
    r"\brm\s+-[a-z]*r",          # rm -r / rm -rf
    r"\brm\s+-rf",
    r"\brmdir\s+/[sq]",          # rmdir /s /q
    r"\brd\s+/[sq]",             # rd /s /q
    r"\bRemove-Item",            # PowerShell 删除
    r"\brmtree",                 # Python shutil.rmtree
    r"\bdel\s+/[fsq]",           # del /f /s /q
    r"\berase\b",
    # 系统破坏类
    r"\bformat\b",
    r"\bmkfs\b",
    r"\bfdisk\b",
    r"\bdiskpart\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\btaskkill\s+/f",
    r"\breg\s+delete\b",
    r"\bsetx\b",
    r"\breg\s+add\b.*\\Environment",
    # 下载执行类
    r"curl\b.*\|",               # curl | sh
    r"wget\b.*\|",
    r"iwr\b.*\|",                # PowerShell Invoke-WebRequest |
    r"\biex\b",                  # Invoke-Expression
    r"powershell\s+-enc",
    r"Invoke-Expression",
    # 清空环境变量
    r"\$env:\w+\s*=\s*['\"]{2}",
    r"\bset\s+\w+\s*=\s*$",
    # 设备写入
    r">\s*/dev/",
    r"\bdd\s+of=",
]

_DANGEROUS_REGEX = re.compile("|".join(DANGEROUS_PATTERNS), re.IGNORECASE)


def _check_dangerous(command: str) -> Optional[str]:
    """检查命令是否命中黑名单，命中返回原因"""
    match = _DANGEROUS_REGEX.search(command)
    if match:
        return match.group(0)
    return None


def _truncate(text: str, limit: Optional[int] = None) -> str:
    """截断输出"""
    if limit is None:
        limit = int(get_config("cmd_output_limit", 20480))
    if len(text) > limit:
        return text[:limit] + f"\n... [已截断，共 {len(text)} 字符]"
    return text


def execute_command(command: str) -> str:
    """执行 CLI 命令并返回输出

    Args:
        command: 要执行的命令

    Returns:
        命令输出（截断后）
    """
    # ── 安全检查 ──
    if not command or not command.strip():
        return "错误: 命令为空"

    danger = _check_dangerous(command)
    if danger:
        logger.warning("拦截危险命令: %s (命中: %s)", command[:100], danger)
        return (
            f"⛔ 命令已被安全拦截: 检测到危险操作 '{danger}'\n"
            f"命令: {command}\n"
            f"如确需执行，请手动在终端运行。"
        )

    timeout = float(get_config("cmd_timeout", 60))
    working_dir = get_working_dir()

    try:
        # Windows 上保留受控 shell（cmd/powershell 语法无 argv 语义），
        # 但仍过黑名单 + 超时 + 截断
        use_shell = sys.platform == "win32"

        if use_shell:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=working_dir,
            )
        else:
            # 非 Windows：参数化执行（不经过 shell）
            args = shlex.split(command)
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=working_dir,
            )

        output_parts = []

        if result.stdout:
            output_parts.append(f"[stdout]\n{_truncate(result.stdout)}")

        if result.stderr:
            output_parts.append(f"[stderr]\n{_truncate(result.stderr)}")

        if result.returncode != 0:
            output_parts.append(f"[返回码] {result.returncode}")

        if not output_parts:
            return "命令执行成功，无输出"

        return "\n\n".join(output_parts)

    except subprocess.TimeoutExpired:
        return f"错误: 命令执行超时（{timeout:.0f} 秒）"
    except FileNotFoundError:
        return f"错误: 命令未找到: {command.split()[0]}"
    except Exception as e:
        logger.exception("命令执行失败")
        return f"命令执行失败: {e}"


# 注册工具 - 命令执行默认需要用户确认（danger_level=3 最高危）
register_tool(
    name="execute_command",
    description="执行 CLI 终端命令并获取输出结果",
    func=execute_command,
    parameters=[
        {"name": "command", "type": "string", "description": "要执行的命令"},
    ],
    requires_approval=True,
    category="command",
    danger_level=3,
)
