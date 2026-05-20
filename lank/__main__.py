import sys
import json
import os
import shutil
import subprocess
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


FIXED_REPLY = "这个问题很不错，建议问AI"

CONFIG_DIR = Path.home() / ".lank"
CONFIG_FILE = CONFIG_DIR / "config.json"


def render_chat(console: Console, messages: List[Tuple[str, str]]):
    table = Table.grid(expand=True)
    table.add_column(ratio=1)
    chat_text = []
    for role, text in messages:
        ts = datetime.now().strftime("%H:%M:%S")
        if role == "user":
            chat_text.append(f"[bold cyan]{ts} 用户:[/bold cyan] {text}")
        elif role == "assistant":
            chat_text.append(f"[bold magenta]{ts} 助手:[/bold magenta] {text}")
        else:
            chat_text.append(f"[green]{ts} 系统:[/green] {text}")
    body = "\n\n".join(chat_text) or "(空聊天)"
    panel = Panel.fit(Align.left(body), title="lank TUI 聊天", border_style="bright_blue")
    console.print(panel)


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
    messages: List[Tuple[str, str]] = [("system", "欢迎使用 lank TUI — 输入 exit 或 Ctrl-D 退出。")]

    history = InMemoryHistory() if InMemoryHistory is not None else None

    while True:
        try:
            console.clear()
            render_chat(console, messages)
            
            if history is not None:
                user_input = prompt("> ", history=history)
            else:
                user_input = prompt("> ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n已退出。再见!")
            break

        if not user_input:
            continue

        if user_input.strip().lower() in ("exit", "quit"):
            console.print("已退出。再见!")
            break

        messages.append(("user", user_input.strip()))
        # Fixed reply regardless of input
        messages.append(("assistant", FIXED_REPLY))


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
