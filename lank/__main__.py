import sys
import json
import os
import shutil
import subprocess
import time
import random
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

try:
    from prompt_toolkit import prompt
    from prompt_toolkit.history import InMemoryHistory
except Exception:
    prompt = input  # type: ignore
    InMemoryHistory = None  # type: ignore

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.align import Align
from rich.live import Live
from rich.text import Text
from rich.box import ROUNDED, DOUBLE
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.columns import Columns
from rich.layout import Layout


FIXED_REPLY = "这个问题很不错，建议问AI"

CONFIG_DIR = Path.home() / ".lank"
CONFIG_FILE = CONFIG_DIR / "config.json"

# AI 角色配置 - 多种AI头像
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


def get_ai_thinking_animation(frame_index: int) -> str:
    """获取思考动画帧"""
    frame = THINKING_FRAMES[frame_index % len(THINKING_FRAMES)]
    return f"[bold yellow]{frame}[/bold yellow] [cyan]AI 深度思考中...[/cyan]"


def stream_text(console: Console, text: str, speed: float = 0.03):
    """模拟流式输出效果"""
    from rich.text import Text
    
    # 创建一个空的Text对象
    output_text = Text()
    
    # 逐字添加并实时刷新
    for char in text:
        output_text.append(char, style="bold magenta")
        console.print(output_text, end="\r")
        time.sleep(speed)
    
    # 最后正常换行
    console.print()


def render_chat(console: Console, messages: List[Tuple[str, str]], show_avatar: bool = True):
    """渲染聊天界面，带AI头像和酷炫效果"""
    
    chat_lines = []
    
    # 添加顶部装饰
    chat_lines.append("[bold blue]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold blue]")
    chat_lines.append("")
    
    for idx, (role, text) in enumerate(messages):
        ts = datetime.now().strftime("%H:%M:%S")
        
        if role == "user":
            # 用户消息 - 右侧对齐，带渐变效果
            user_line = f"[dim]{ts}[/dim] [bold cyan]👤 你:[/bold cyan] {text}"
            chat_lines.append(f"[right]{user_line}[/right]")
            chat_lines.append("")
            
        elif role == "assistant":
            # AI消息 - 左侧对齐，带头像和特殊效果
            avatar_idx = idx % len(AI_AVATARS)
            avatar = AI_AVATARS[avatar_idx]
            
            if show_avatar:
                ai_header = f"[bold magenta]🤖 AI 智能助手[/bold magenta] [dim]{ts}[/dim]"
                chat_lines.append(ai_header)
                
                # 添加ASCII头像，带颜色
                avatar_lines = avatar.split('\n')
                for line in avatar_lines:
                    chat_lines.append(f"[magenta]{line}[/magenta]")
                
                # 回复内容带打字机效果标记
                chat_lines.append(f"[bold green]💬 回复:[/bold green] [italic]{text}[/italic]")
            else:
                ai_line = f"[dim]{ts}[/dim] [bold magenta]🤖 AI:[/bold magenta] {text}"
                chat_lines.append(ai_line)
            chat_lines.append("")
            
        else:
            # 系统消息 - 居中显示
            sys_line = f"[green]⚙️ {text}[/green]"
            chat_lines.append(f"[center]{sys_line}[/center]")
            chat_lines.append("")
    
    # 添加底部装饰
    chat_lines.append("[bold blue]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold blue]")
    
    body = "\n".join(chat_lines) or "[dim](开始新的对话...)[/dim]"
    
    # 创建更美观的面板，使用双层边框
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
    """显示酷炫的思考动画"""
    frames_count = int(duration * 10)  # 每秒10帧
    
    with Live(refresh_per_second=10) as live:
        for i in range(frames_count):
            frame = THINKING_FRAMES[i % len(THINKING_FRAMES)]
            bar = LOADING_BARS[i % len(LOADING_BARS)]
            
            # 创建进度条效果
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


def ensure_config_dir():
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def is_scripts_dir_on_path(scripts_dir: str) -> bool:
    paths = os.environ.get("PATH", os.defpath).split(os.pathsep)
    return str(scripts_dir) in paths


def try_add_scripts_to_path(console: Console, scripts_dir: str):
    console.print(f"检测到 `{scripts_dir}` 未在环境变量 PATH 中。")
    if os.name == "nt":
        console.print("是否现在将其添加到当前用户 PATH？(将使用 `setx` 添加,需重启终端生效) [y/N]")
        ans = input().strip().lower()
        if ans == "y":
            try:
                # Use setx to modify user PATH
                new_path = os.environ.get("PATH", "")
                if str(scripts_dir) not in new_path:
                    cmd = ["setx", "PATH", new_path + os.pathsep + str(scripts_dir)]
                    subprocess.check_call(cmd, shell=True)
                    console.print("已尝试将 Scripts 目录添加到用户 PATH。请重启终端以生效。")
            except Exception as e:
                console.print(f"添加 PATH 失败: {e}")
    else:
        console.print(f"在类 Unix 系统上,请将 `{scripts_dir}` 添加到你的 shell 配置文件(例如 ~/.bashrc 或 ~/.profile)。")


def run_first_run_guide(console: Console):
    ensure_config_dir()
    cfg = {}
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}

    if cfg.get("completed"):
        return

    console.print(Panel("欢迎使用 lank!接下来将帮助你完成环境配置(只需交互确认)。", title="首次引导"))

    # 1) 检查依赖
    missing = []
    try:
        import rich  # noqa: F401
    except Exception:
        missing.append("rich")
    try:
        import prompt_toolkit  # noqa: F401
    except Exception:
        missing.append("prompt_toolkit")

    if missing:
        console.print(f"检测到缺少依赖: {', '.join(missing)}")
        console.print("是否现在使用 pip 安装这些依赖?[y/N]")
        ans = input().strip().lower()
        if ans == "y":
            try:
                cmd = [sys.executable, "-m", "pip", "install"] + missing
                subprocess.check_call(cmd)
                console.print("依赖安装完成。")
            except Exception as e:
                console.print(f"安装依赖失败: {e}")

    # 2) 提示用户将本项目安装为可执行工具(生成 `lank` 启动器)
    console.print("推荐将当前包安装为可执行工具,这样可以在任意终端直接输入 `lank tui` 启动。是否现在安装(pip install --user .)?[y/N]")
    ans = input().strip().lower()
    if ans == "y":
        try:
            project_root = Path(__file__).resolve().parents[1]
            cmd = [sys.executable, "-m", "pip", "install", "--user", str(project_root)]
            subprocess.check_call(cmd)
            console.print("已通过 `pip install --user .` 安装。")
        except Exception as e:
            console.print(f"安装失败: {e}")

    # 3) 检查 Scripts dir 是否在 PATH
    scripts_dir = Path(sys.executable).parent / ("Scripts" if os.name == "nt" else "bin")
    if not is_scripts_dir_on_path(str(scripts_dir)):
        try_add_scripts_to_path(console, str(scripts_dir))

    # mark completed
    try:
        CONFIG_FILE.write_text(json.dumps({"completed": True}), encoding="utf-8")
    except Exception:
        pass


def run_tui():
    console = Console()
    messages: List[Tuple[str, str]] = [("system", "欢迎使用 LANK AI — 你的智能聊天助手 🚀")]

    history = InMemoryHistory() if InMemoryHistory is not None else None

    # 显示酷炫的欢迎信息
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
    time.sleep(1)

    while True:
        try:
            console.clear()
            render_chat(console, messages, show_avatar=True)
            
            # 显示输入提示符
            console.print("\n[bold yellow]➤ 请输入您的问题:[/bold yellow] ", end="")
            
            if history is not None:
                user_input = prompt("", history=history)
            else:
                user_input = prompt("")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[bold red]感谢使用 LANK AI！再见! 👋[/bold red]")
            break

        if not user_input:
            continue

        if user_input.strip().lower() in ("exit", "quit"):
            console.print("\n[bold green]感谢使用 LANK AI！祝您有美好的一天! 🌟[/bold green]")
            break

        messages.append(("user", user_input.strip()))
        
        # 显示思考动画
        console.print("\n[dim]--- AI 正在思考 ---[/dim]\n")
        show_thinking_animation(console, duration=random.uniform(1.0, 2.0))
        
        # 流式输出回复
        console.print("\n[bold magenta]🤖 AI 助手:[/bold magenta] ", end="")
        stream_text(console, FIXED_REPLY, speed=0.02)
        
        messages.append(("assistant", FIXED_REPLY))
        
        # 短暂暂停让用户看清
        time.sleep(0.5)


def cli(argv=None):
    argv = argv or sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print("用法: python -m lank tui\n       或在 Windows 下运行: lank.cmd tui")
        return 0

    cmd = argv[0]
    if cmd == "tui":
        run_tui()
    else:
        print(f"未知命令: {cmd}")
        return 2


if __name__ == "__main__":
    raise SystemExit(cli())
