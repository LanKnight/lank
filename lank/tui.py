"""
TUI 聊天界面模块
支持普通聊天模式和 AI 智能模式
"""

import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import load_config, get_config
from .memory import save_conversation, get_recent_context, get_profile_summary

# Rich 导入
from rich.console import Console
from rich.panel import Panel
from rich.align import Align
from rich.live import Live
from rich.text import Text
from rich.box import ROUNDED, DOUBLE
from rich.table import Table

# Prompt toolkit
try:
    from prompt_toolkit import prompt
    from prompt_toolkit.history import InMemoryHistory
except Exception:
    prompt = input  # type: ignore
    InMemoryHistory = None  # type: ignore


# 常量
FIXED_REPLY = "这个问题很不错，建议问AI"
AI_AVATARS = [
    """
╭───────────╮
│  ◉     ◉  │
│     ◡     │
│  ╰─────╯  │
╰───────────╯""",
    """
┌───────────┐
│ ★     ★   │
│    ▽      │
│  └─────┘  │
└───────────┘""",
    """
◢───────────◣
│  ●     ●  │
│    ◠      │
│  ╰─────╯  │
◥───────────◤"""
]

THINKING_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
LOADING_BARS = ["▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]


def render_chat(console: Console, messages: List[Tuple[str, str]], show_avatar: bool = True):
    """渲染聊天界面"""
    chat_lines = []
    chat_lines.append("[bold blue]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold blue]")
    chat_lines.append("")
    
    for idx, (role, text) in enumerate(messages):
        ts = datetime.now().strftime("%H:%M:%S")
        
        if role == "user":
            user_line = f"[dim]{ts}[/dim] [bold cyan]👤 你:[/bold cyan] {text}"
            chat_lines.append(f"[right]{user_line}[/right]")
            chat_lines.append("")
        elif role == "assistant":
            avatar_idx = idx % len(AI_AVATARS)
            avatar = AI_AVATARS[avatar_idx]
            
            if show_avatar:
                ai_header = f"[bold magenta]🤖 AI 智能助手[/bold magenta] [dim]{ts}[/dim]"
                chat_lines.append(ai_header)
                avatar_lines = avatar.split('\n')
                for line in avatar_lines:
                    chat_lines.append(f"[magenta]{line}[/magenta]")
                chat_lines.append(f"[bold green]💬 回复:[/bold green] [italic]{text}[/italic]")
            else:
                ai_line = f"[dim]{ts}[/dim] [bold magenta]🤖 AI:[/bold magenta] {text}"
                chat_lines.append(ai_line)
            chat_lines.append("")
        else:
            sys_line = f"[green]⚙️ {text}[/green]"
            chat_lines.append(f"[center]{sys_line}[/center]")
            chat_lines.append("")
    
    chat_lines.append("[bold blue]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold blue]")
    
    body = "\n".join(chat_lines) or "[dim](开始新的对话...)[/dim]"
    
    panel = Panel(
        Align.left(body),
        title="[bold rainbow]✨ LANK AI 聊天室 ✨[/bold rainbow]",
        subtitle=f"[dim]在线 • {datetime.now().strftime('%Y-%m-%d')}[/dim]",
        border_style="bright_cyan",
        box=DOUBLE,
        padding=(1, 2),
        highlight=True
    )
    console.print(panel)


def show_thinking_animation(console: Console, duration: float = 1.5):
    """显示思考动画"""
    frames_count = int(duration * 10)
    
    with Live(refresh_per_second=10) as live:
        for i in range(frames_count):
            frame = THINKING_FRAMES[i % len(THINKING_FRAMES)]
            bar = LOADING_BARS[i % len(LOADING_BARS)]
            
            progress_width = 30
            filled = int((i / frames_count) * progress_width)
            progress_bar = bar * filled + "░" * (progress_width - filled)
            
            animation_text = f"""
[bold yellow]{frame}[/bold yellow] [cyan]AI 神经网络处理中...[/cyan]

[dim]处理进度:[/dim] [yellow]{progress_bar}[/yellow] [bold]{int((i / frames_count) * 100)}%[/bold]

[dim]正在分析语义 • 生成响应 • 优化表达[/dim]
            """.strip()
            
            thinking_panel = Panel(
                Align.center(animation_text),
                title="[bold yellow]🧠 思考中[/bold yellow]",
                border_style="yellow",
                box=ROUNDED,
                padding=(1, 2)
            )
            live.update(thinking_panel)
            time.sleep(0.1)


def stream_text(console: Console, text: str, speed: float = 0.03):
    """模拟流式输出效果"""
    output_text = Text()
    for char in text:
        output_text.append(char, style="bold magenta")
        console.print(output_text, end="\r")
        time.sleep(speed)
    console.print()


def run_tui():
    """运行 TUI 聊天界面"""
    console = Console()
    messages: List[Tuple[str, str]] = [("system", "欢迎使用 LANK AI — 你的智能聊天助手 🚀")]
    
    history = InMemoryHistory() if InMemoryHistory is not None else None
    
    # 显示欢迎信息
    welcome_art = """
[bold cyan]
╔══════════════════════════════════════════════════╗
║                                                  ║
║     ██      █████  ███    ██ ██   ██             ║
║     ██     ██   ██ ████   ██ ██ ██               ║
║     ██     ███████ ██ ██  ██ ███                 ║
║     ██     ██   ██ ██  ██ ██ ██ ██               ║
║     ██████ ██   ██ ██   ████ ██   ██             ║
║                                                  ║
║         🤖 智能 AI 聊天助手 v2.0 🤖              ║
║                                                  ║
╚══════════════════════════════════════════════════╝
[/bold cyan]
    """
    console.print(welcome_art)
    console.print("\n[bold green]✨ 全新升级 | 流式输出 | 思考动画 | 酷炫界面[/bold green]\n")
    console.print("[dim]💡 输入 /ai 切换到 AI 智能模式 | /help 查看帮助 | exit 退出[/dim]\n")
    time.sleep(1)
    
    # 检查 AI 模式是否可用
    ai_available = False
    try:
        from .ai_client import AIClient
        client = AIClient()
        ready, _ = client.is_ready()
        ai_available = ready
    except Exception:
        pass
    
    ai_mode = False
    ai_history: List[Dict[str, Any]] = []
    
    while True:
        try:
            console.clear()
            render_chat(console, messages, show_avatar=True)
            
            # 显示模式指示
            mode_indicator = "[bold yellow]🤖 AI[/bold yellow]" if ai_mode else "[bold cyan]💬 普通[/bold cyan]"
            console.print(f"\n[{mode_indicator}] ", end="")
            
            if history is not None:
                user_input = prompt("", history=history)
            else:
                user_input = prompt("")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[bold red]感谢使用 LANK AI！再见! 👋[/bold red]")
            break
        
        if not user_input:
            continue
        
        # 处理命令
        if user_input.strip().lower() in ("exit", "quit"):
            console.print("\n[bold green]感谢使用 LANK AI！祝您有美好的一天! 🌟[/bold green]")
            break
        
        if user_input.strip().startswith("/"):
            cmd = user_input.strip().lower()
            if cmd == "/ai":
                if ai_available:
                    ai_mode = True
                    messages.append(("system", "已切换到 AI 智能模式 🧠"))
                else:
                    messages.append(("system", "⚠️ AI 模式不可用，请先配置 API Key (lank set)"))
                continue
            elif cmd == "/normal":
                ai_mode = False
                messages.append(("system", "已切换到普通聊天模式 💬"))
                continue
            elif cmd == "/help":
                messages.append(("system", """
可用命令:
  /ai     - 切换到 AI 智能模式（需配置 API Key）
  /normal - 切换到普通聊天模式
  /help   - 显示此帮助
  /clear  - 清空对话
  /save   - 保存对话
  exit    - 退出程序
                """.strip()))
                continue
            elif cmd == "/clear":
                messages = [("system", "对话已清空 🧹")]
                ai_history = []
                continue
            elif cmd == "/save":
                session_id = save_conversation(ai_history) if ai_history else ""
                if session_id:
                    messages.append(("system", f"✅ 对话已保存 (ID: {session_id})"))
                else:
                    messages.append(("system", "⚠️ 保存失败或记忆功能未开启"))
                continue
            else:
                messages.append(("system", f"未知命令: {cmd}，输入 /help 查看帮助"))
                continue
        
        messages.append(("user", user_input.strip()))
        
        if ai_mode and ai_available:
            # AI 模式
            try:
                from .ai_client import AIClient
                
                ai_history.append({"role": "user", "content": user_input.strip()})
                
                # 显示思考动画
                console.print("\n[dim]--- AI 正在思考 ---[/dim]\n")
                show_thinking_animation(console, duration=1.0)
                
                client = AIClient()
                
                def on_tool_call(name, args, result=None):
                    if result is None:
                        # 需要确认
                        console.print(f"\n[bold yellow]🔧 AI 想要调用工具: {name}[/bold yellow]")
                        console.print(f"   参数: {json.dumps(args, ensure_ascii=False)}")
                        console.print("[bold]   是否允许? [Y/n]: [/bold]", end="")
                        ans = input().strip().lower()
                        return ans not in ("n", "no")
                    else:
                        console.print(f"\n[bold cyan]🔧 工具 [{name}] 执行结果:[/bold cyan]")
                        result_str = str(result)
                        if len(result_str) > 300:
                            result_str = result_str[:300] + "..."
                        console.print(f"   {result_str}")
                        return True
                
                success, response, ai_history = client.chat(
                    messages=ai_history,
                    stream=False,
                    on_tool_call=on_tool_call,
                )
                
                if success:
                    messages.append(("assistant", response))
                else:
                    messages.append(("system", f"⚠️ {response}"))
                
                # 保存对话
                save_conversation(ai_history)
                
            except Exception as e:
                messages.append(("system", f"⚠️ AI 调用失败: {e}"))
        else:
            # 普通模式 - 固定回复
            console.print("\n[dim]--- AI 正在思考 ---[/dim]\n")
            show_thinking_animation(console, duration=random.uniform(1.0, 2.0))
            
            console.print("\n[bold magenta]🤖 AI 助手:[/bold magenta] ", end="")
            stream_text(console, FIXED_REPLY, speed=0.02)
            
            messages.append(("assistant", FIXED_REPLY))
        
        time.sleep(0.5)
