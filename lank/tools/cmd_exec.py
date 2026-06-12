"""
命令执行工具 - 运行 CLI 命令
类似 Claude 的命令执行能力
"""

import os
import subprocess
import sys
import tempfile
from typing import Optional

from . import register_tool


def execute_command(command: str, requires_approval: bool = True) -> str:
    """执行 CLI 命令并返回输出
    
    Args:
        command: 要执行的命令
        requires_approval: 是否需要用户确认（由 AI 调用时自动设置）
    
    Returns:
        命令输出
    """
    try:
        # 在 Windows 上使用 shell=True
        use_shell = sys.platform == "win32"
        
        # 执行命令，设置超时防止无限运行
        result = subprocess.run(
            command,
            shell=use_shell,
            capture_output=True,
            text=True,
            timeout=60,  # 60 秒超时
            cwd=os.getcwd(),
        )
        
        output_parts = []
        
        if result.stdout:
            output_parts.append(f"[stdout]\n{result.stdout}")
        
        if result.stderr:
            output_parts.append(f"[stderr]\n{result.stderr}")
        
        if result.returncode != 0:
            output_parts.append(f"[返回码] {result.returncode}")
        
        if not output_parts:
            return "命令执行成功，无输出"
        
        return "\n\n".join(output_parts)
    
    except subprocess.TimeoutExpired:
        return "错误: 命令执行超时（60 秒）"
    except FileNotFoundError:
        return f"错误: 命令未找到: {command.split()[0]}"
    except Exception as e:
        return f"命令执行失败: {e}"


# 注册工具 - 注意：命令执行默认需要用户确认
register_tool(
    name="execute_command",
    description="执行 CLI 终端命令并获取输出结果",
    func=execute_command,
    parameters=[
        {"name": "command", "type": "string", "description": "要执行的命令"},
    ],
    requires_approval=True,
)
