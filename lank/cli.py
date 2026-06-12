"""
CLI 命令处理模块
处理 lank tui / lank ai / lank set 等命令
"""

import json
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from .config import run_set_command, load_config, get_config
from .tui import run_tui
from .memory import save_conversation, get_recent_context

# Rich 导入
from rich.console import Console
from rich.panel import Panel
from rich.align import Align
from rich.live import Live
from rich.text import Text
from rich.box import ROUNDED, DOUBLE
from rich.table import Table
from rich.markdown import Markdown


def print_help():
    """打印帮助信息"""
    print("""
╔══════════════════════════════════════════════════╗
║              LANK - 私人 AI 终端助手              ║
║                  v0.2.0                          ║
╚══════════════════════════════════════════════════╝

用法:
  lank tui             启动 TUI 聊天界面（支持 /ai 切换 AI 模式）
  lank ai [问题]       启动 AI 聊天界面（可带初始问题）
  lank set             交互式配置向导
  lank set show        查看当前配置
  lank set reset       重置配置
  lank set get <key>   获取配置项
  lank set set <k> <v> 设置配置项
  lank help            显示此帮助

示例:
  lank tui             启动聊天界面
  lank ai              启动 AI 聊天界面
  lank ai 你好         启动 AI 聊天界面并打招呼
  lank ai 帮我读一下readme.md   AI 读取文件
  lank set             配置 API Key 等
""")


def render_ai_message(console: Console, role: str, content: str, ts: str = ""):
    """渲染一条 AI 聊天消息"""
    if not ts:
        ts = datetime.now().strftime("%H:%M:%S")
    
    if role == "user":
        text = Text(f"  👤 你: {content}", style="bold cyan")
        console.print(Panel(
            Align.right(text),
            border_style="cyan",
            box=ROUNDED,
            padding=(0, 1),
            width=console.width - 2,
        ))
    elif role == "assistant":
        text = Text(f"  🤖 AI: {content}", style="bold magenta")
        console.print(Panel(
            Align.left(text),
            border_style="magenta",
            box=ROUNDED,
            padding=(0, 1),
            width=console.width - 2,
        ))
    elif role == "system":
        console.print(f"  [dim]{ts}[/dim] [green]⚙️ {content}[/green]")
    elif role == "tool":
        # 工具调用结果用更紧凑的格式
        result_str = str(content)
        if len(result_str) > 300:
            result_str = result_str[:300] + "..."
        console.print(Panel(
            Text(f"  🔧 {result_str}", style="dim yellow"),
            border_style="yellow",
            box=ROUNDED,
            padding=(0, 1),
            width=console.width - 2,
            title="工具结果",
        ))


def show_ai_thinking(console: Console, duration: float = 1.0):
    """显示 AI 思考动画"""
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    steps = int(duration * 10)
    
    for i in range(steps):
        frame = frames[i % len(frames)]
        console.print(f"\r  [bold yellow]{frame}[/bold yellow] [cyan]AI 思考中...[/cyan]", end="")
        time.sleep(0.1)
    console.print("\r" + " " * 40 + "\r", end="")


def run_ai_chat(initial_question: Optional[str] = None):
    """运行 AI 聊天界面（带 Rich 渲染的交互式对话）
    
    Args:
        initial_question: 初始问题（可选）
    """
    console = Console()
    
    # 检查配置
    config = load_config()
    if not config.get("api_key"):
        console.print("[bold red]❌ 未配置 API Key，请先执行: lank set[/bold red]")
        return 1
    
    try:
        from .ai_client import AIClient
    except ImportError:
        console.print("[bold red]❌ 缺少 openai 库，请执行: pip install openai[/bold red]")
        return 1
    
    client = AIClient()
    ready, msg = client.is_ready()
    if not ready:
        console.print(f"[bold red]❌ {msg}[/bold red]")
        return 1
    
    ai_name = config.get("ai_name", "LANK")
    user_name = config.get("user_name", "用户")
    
    # 清屏并显示欢迎界面
    console.clear()
    
    # 显示标题
    title = Panel(
        Align.center(
            f"[bold cyan]🤖 {ai_name} AI 聊天[/bold cyan]\n"
            f"[dim]输入 exit 退出 | /clear 清空 | /help 帮助[/dim]"
        ),
        border_style="bright_cyan",
        box=DOUBLE,
        padding=(1, 2),
    )
    console.print(title)
    console.print()
    
    history: List[Dict[str, Any]] = []
    display_messages: List[tuple] = []  # (role, content)
    
    # 如果有初始问题，先处理
    if initial_question:
        display_messages.append(("user", initial_question))
        history.append({"role": "user", "content": initial_question})
        
        # 显示用户消息
        render_ai_message(console, "user", initial_question)
        console.print()
        
        # 显示思考动画
        show_ai_thinking(console, duration=1.0)
        
        # 调用 AI
        def on_tool_call(name, args, result=None):
            if result is None:
                # 需要确认
                console.print(f"\n  [bold yellow]🔧 AI 想要调用工具: {name}[/bold yellow]")
                console.print(f"     [dim]参数: {json.dumps(args, ensure_ascii=False)}[/dim]")
                console.print("  [bold]是否允许? [Y/n]: [/bold]", end="")
                ans = input().strip().lower()
                return ans not in ("n", "no")
            else:
                # 显示工具结果
                render_ai_message(console, "tool", str(result))
                console.print()
                return True
        
        def on_text(text):
            if text:
                render_ai_message(console, "assistant", text)
                console.print()
        
        success, response, history = client.chat(
            messages=history,
            stream=False,
            on_tool_call=on_tool_call,
            on_text=on_text,
        )
        
        if not success:
            console.print(f"  [bold red]❌ {response}[/bold red]")
            console.print()
        
        # 保存对话
        save_conversation(history)
    
    # 主循环
    while True:
        try:
            # 显示输入提示
            console.print(f"  [bold cyan]┌─[/bold cyan] [bold]{user_name}[/bold]")
            console.print(f"  [bold cyan]├[/bold cyan] ", end="")
            user_input = input().strip()
        except (EOFError, KeyboardInterrupt):
            console.print(f"\n  [bold cyan]└─[/bold cyan] [dim]再见! 👋[/dim]\n")
            break
        
        if not user_input:
            continue
        
        # 处理命令
        if user_input.lower() in ("exit", "quit"):
            console.print(f"  [bold cyan]└─[/bold cyan] [bold green]感谢使用 {ai_name}！再见! 👋[/bold green]\n")
            break
        
        if user_input.startswith("/"):
            cmd = user_input.lower()
            if cmd == "/clear":
                history = []
                display_messages = []
                console.clear()
                console.print(title)
                console.print("  [green]✅ 对话已清空[/green]\n")
                continue
            elif cmd == "/help":
                console.print("""
  [bold]可用命令:[/bold]
    /clear  清空对话历史
    /help   显示此帮助
    /save   保存对话
    /stats  显示使用统计
    /theme  显示当前主题
    exit    退出程序
                """.strip() + "\n")
                continue
            elif cmd == "/save":
                session_id = save_conversation(history) if history else ""
                if session_id:
                    console.print(f"  [green]✅ 对话已保存 (ID: {session_id})[/green]\n")
                else:
                    console.print("  [yellow]⚠️ 保存失败或记忆功能未开启[/yellow]\n")
                continue
            elif cmd == "/stats":
                try:
                    from .utils import get_stats_summary
                    console.print(f"  {get_stats_summary()}\n")
                except Exception:
                    console.print("  [yellow]⚠️ 无法获取统计[/yellow]\n")
                continue
            elif cmd == "/theme":
                try:
                    from .utils import list_themes
                    console.print(f"  {list_themes()}\n")
                except Exception:
                    pass
                continue
            else:
                console.print(f"  [yellow]⚠️ 未知命令: {cmd}，输入 /help 查看帮助[/yellow]\n")
                continue
        
        # 显示用户消息
        render_ai_message(console, "user", user_input)
        console.print()
        
        # 添加到历史
        history.append({"role": "user", "content": user_input})
        
        # 显示思考动画
        show_ai_thinking(console, duration=0.8)
        
        # 调用 AI
        def on_tool_call(name, args, result=None):
            if result is None:
                console.print(f"\n  [bold yellow]🔧 AI 想要调用工具: {name}[/bold yellow]")
                console.print(f"     [dim]参数: {json.dumps(args, ensure_ascii=False)}[/dim]")
                console.print("  [bold]是否允许? [Y/n]: [/bold]", end="")
                ans = input().strip().lower()
                return ans not in ("n", "no")
            else:
                render_ai_message(console, "tool", str(result))
                console.print()
                return True
        
        def on_text(text):
            if text:
                render_ai_message(console, "assistant", text)
                console.print()
        
        success, response, history = client.chat(
            messages=history,
            stream=False,
            on_tool_call=on_tool_call,
            on_text=on_text,
        )
        
        if not success:
            console.print(f"  [bold red]❌ {response}[/bold red]")
            console.print()
        
        # 保存对话
        save_conversation(history)
    
    return 0


def cli(argv: Optional[List[str]] = None) -> int:
    """主 CLI 入口
    
    Args:
        argv: 命令行参数列表
    
    Returns:
        退出码
    """
    if argv is None:
        argv = sys.argv[1:]
    
    if not argv or argv[0] in ("-h", "--help", "help"):
        print_help()
        return 0
    
    cmd = argv[0]
    
    if cmd == "tui":
        run_tui()
        return 0
    
    elif cmd == "ai":
        # 无论是否有参数，都启动聊天界面
        # 如果有参数，作为初始问题传入
        initial_question = " ".join(argv[1:]) if len(argv) > 1 else None
        return run_ai_chat(initial_question)
    
    elif cmd == "set":
        return run_set_command(argv[1:])
    
    elif cmd == "version" or cmd == "-v" or cmd == "--version":
        from . import __version__
        print(f"lank v{__version__}")
        return 0
    
    else:
        print(f"未知命令: {cmd}")
        print("使用 'lank help' 查看帮助")
        return 2
