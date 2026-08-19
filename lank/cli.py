"""
CLI 命令处理模块
处理 lank tui / lank ai / lank set 等命令
"""

import json
import os
import sys
from typing import Any, Dict, List, Optional


from .config import run_set_command, load_config, get_config
from .logs import setup_logging
from .tui import run_tui
from .memory import save_conversation

# 初始化日志系统
setup_logging()

# Rich 导入
from rich.console import Console
from rich.panel import Panel
from rich.align import Align
from rich.box import DOUBLE


def print_help():
    """打印帮助信息"""
    from . import __version__
    print(f"""
╔══════════════════════════════════════════════════╗
║              LANK - 私人 AI 终端助手              ║
║                  v{__version__:<29}║
╚══════════════════════════════════════════════════╝

用法:
  lank tui             启动 TUI 聊天界面（支持 /ai 切换 AI 模式）
  lank ai [问题]       启动 AI 聊天界面（可带初始问题）
  lank set             交互式配置向导
  lank set show        查看当前配置
  lank set reset       重置配置
  lank set verify      验证配置是否正确
  lank set get <key>   获取配置项
  lank set set <k> <v> 设置配置项
  lank install         一键安装到系统（在任何目录下使用 lank）
  lank doctor          诊断环境问题
  lank help            显示此帮助

示例:
  lank tui             启动聊天界面
  lank ai              启动 AI 聊天界面
  lank ai 你好         启动 AI 聊天界面并打招呼
  lank ai 帮我读一下readme.md   AI 读取文件
  lank set             配置 API Key 等
  lank install         安装到系统 PATH
  lank doctor          检查环境配置

聊天命令:
  /ai /normal          切换 AI/普通模式 (TUI)
  /clear               清空对话历史
  /save                保存对话
  /stats               显示使用统计
  /theme [名称]        显示/切换主题 (default/dark/cyberpunk/hacker/sunset)
  /model [名称]        显示/切换 AI 模型
  /export [json]       导出对话为 Markdown 或 JSON
  /todo list|add|done|del  管理待办事项
  /update              检查更新
""")



def render_ai_message(console: Console, role: str, content: str, ts: str = ""):
    """渲染一条 AI 聊天消息 — 简洁无边框"""
    from .utils import get_theme

    theme = get_theme()

    if role == "user":
        console.print(
            f"  [bold {theme['user_color']}]▸ 你:[/bold {theme['user_color']}] {content}"
        )
    elif role == "assistant":
        console.print(
            f"  [bold {theme['ai_color']}]▸ AI:[/bold {theme['ai_color']}] {content}"
        )
    elif role == "system":
        console.print(f"  [dim {theme['system_color']}]⚙ {content}[/dim {theme['system_color']}]")
    elif role == "tool":
        result_str = str(content)
        if len(result_str) > 300:
            result_str = result_str[:300] + "..."
        console.print(f"  [dim yellow]🔧 {result_str}[/dim yellow]")


def run_ai_chat(initial_question: Optional[str] = None):
    """运行 AI 聊天界面（全屏：输入框固定底部，内容上滚）

    复用 tui.ChatApp（ai_only 模式），所有交互在固定输入框完成。

    Args:
        initial_question: 初始问题（可选）
    """
    config = load_config()
    if not config.get("api_key"):
        print("❌ 未配置 API Key，请先执行: lank set")
        return 1

    try:
        from .ai_client import AIClient
    except ImportError:
        print("❌ 缺少 openai 库，请执行: pip install openai")
        return 1

    client = AIClient()
    ready, msg = client.is_ready()
    if not ready:
        print(f"❌ {msg}")
        return 1

    from .tui import run_ai_chat as _tui_ai_chat
    return _tui_ai_chat(initial_question, client=client)


def run_install():
    """运行一键安装（将 lank 安装到系统 PATH）"""
    console = Console()
    
    title = Panel(
        Align.center("[bold cyan]🚀 LANK 一键安装[/bold cyan]"),
        border_style="bright_cyan",
        box=DOUBLE,
        padding=(1, 2),
    )
    console.print(title)
    console.print()
    
    # 检查 Python 环境
    console.print("[bold]🔍 检查 Python 环境...[/bold]")
    import sys as sys_module
    py_version = f"{sys_module.version_info.major}.{sys_module.version_info.minor}.{sys_module.version_info.micro}"
    console.print(f"  ✅ Python {py_version}")
    console.print()
    
    # 检查是否已安装
    try:
        from . import __version__
        console.print(f"[bold]📦 当前版本:[/bold] v{__version__}")
    except Exception:
        pass
    
    console.print("[bold]📦 正在安装 LANK 到系统...[/bold]")
    console.print("  [dim]执行: pip install --user -e .[/dim]")
    console.print()
    
    # 执行安装
    import subprocess
    import os
    
    # 获取当前项目目录
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--user", "-e", project_dir],
            capture_output=True,
            text=True,
            timeout=120,
        )
        
        if result.returncode == 0:
            console.print("[bold green]✅ 安装成功！[/bold green]")
            console.print()
            console.print("[bold]现在你可以在任何目录下使用 lank 命令了！[/bold]")
            console.print()
            console.print("  [bold yellow]⚠️ 重要：请重启终端后 lank 命令才能生效！[/bold yellow]")
            console.print()
            console.print("  用法示例（重启终端后）:")
            console.print("    lank tui         启动聊天界面")
            console.print("    lank ai          启动 AI 聊天")
            console.print("    lank set         配置向导")
            console.print("    lank doctor      诊断环境")
            console.print()
            console.print("  [dim]如果不想重启终端，也可以使用以下方式运行：[/dim]")
            console.print(f"    [dim]py -m lank [命令][/dim]")
            console.print()

            
            # 检查 lank 命令是否在 PATH 中，并尝试自动添加
            if sys.platform == "win32":
                user_base = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Python")
                scripts_dirs = []
                if os.path.isdir(user_base):
                    for root, dirs, _ in os.walk(user_base):
                        for d in dirs:
                            scripts_dir = os.path.join(root, d, "Scripts")
                            if os.path.isdir(scripts_dir):
                                scripts_dirs.append(scripts_dir)
                        break
                
                if scripts_dirs:
                    scripts_dir = scripts_dirs[0]
                    # 检查是否已在用户 PATH 中（通过注册表）
                    try:
                        reg_result = subprocess.run(
                            ["reg", "query", "HKCU\\Environment", "/v", "PATH"],
                            capture_output=True, text=True, timeout=10,
                        )
                        user_path = ""
                        if reg_result.returncode == 0:
                            # 解析注册表输出
                            for line in reg_result.stdout.splitlines():
                                if "REG_SZ" in line or "REG_EXPAND_SZ" in line:
                                    parts = line.split("REG_SZ")
                                    if len(parts) > 1:
                                        user_path = parts[1].strip()
                                    elif len(line.split("REG_EXPAND_SZ")) > 1:
                                        user_path = line.split("REG_EXPAND_SZ")[1].strip()
                                    break
                        
                        if scripts_dir.lower() not in user_path.lower():
                            # 使用 reg add 追加到用户 PATH（避免 setx 的截断问题）
                   
                            if user_path:
                                new_path = f"{user_path};{scripts_dir}"
                            else:
                                new_path = scripts_dir
                            
                            result = subprocess.run(
                                ["reg", "add", "HKCU\\Environment", "/v", "PATH", "/t", "REG_EXPAND_SZ", "/d", new_path, "/f"],
                                capture_output=True, text=True, timeout=10,
                            )
                            if result.returncode == 0:
                                console.print("[bold green]✅ 已自动将 Scripts 目录添加到系统 PATH！[/bold green]")
                                console.print(f"   目录: {scripts_dir}")
                                console.print("[bold yellow]⚠️ 请重启终端后 lank 命令才能生效[/bold yellow]")
                            else:
                                raise Exception(result.stderr or "reg add failed")
                        else:
                            console.print("[bold green]✅ Scripts 目录已在 PATH 中[/bold green]")
                    except Exception as e:
                        console.print(f"[bold yellow]💡 提示:[/bold yellow] 请手动将以下目录添加到系统 PATH：")
                        console.print(f"    {scripts_dir}")
                        console.print(f"   方法: 系统属性 → 环境变量 → 用户变量 → PATH → 新建")
                    console.print()


        else:
            console.print("[bold red]❌ 安装失败！[/bold red]")
            console.print(f"  {result.stderr}")
            console.print()
            console.print("[bold]请尝试手动安装:[/bold]")
            console.print(f"  cd {project_dir}")
            console.print("  pip install --user -e .")
            console.print()
    except subprocess.TimeoutExpired:
        console.print("[bold red]❌ 安装超时，请检查网络连接后重试[/bold red]")
    except Exception as e:
        console.print(f"[bold red]❌ 安装出错: {e}[/bold red]")
    
    return 0


def run_doctor():
    """诊断环境问题"""
    console = Console()
    
    title = Panel(
        Align.center("[bold cyan]🔍 LANK 环境诊断[/bold cyan]"),
        border_style="bright_cyan",
        box=DOUBLE,
        padding=(1, 2),
    )
    console.print(title)
    console.print()
    
    issues = []
    
    # 1. 检查 Python 版本
    console.print("[bold]1. Python 环境[/bold]")
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 8):
        console.print(f"  ✅ Python {py_version}")
    else:
        console.print(f"  ❌ Python {py_version}（需要 3.8+）")
        issues.append("Python 版本过低，请升级到 3.8+")
    console.print()
    
    # 2. 检查依赖
    console.print("[bold]2. 核心依赖[/bold]")
    deps = [
        ("rich", "rich"),
        ("prompt_toolkit", "prompt_toolkit"),
    ]
    all_deps_ok = True
    for name, import_name in deps:
        try:
            __import__(import_name)
            console.print(f"  ✅ {name}")
        except ImportError:
            console.print(f"  ❌ {name}（未安装）")
            all_deps_ok = False
            issues.append(f"缺少依赖: {name}，请执行: py -m pip install {name}")
    
    # 检查 openai（可选）
    try:
        import openai
        console.print(f"  ✅ openai (AI 功能可用)")
    except ImportError:
        console.print(f"  ⚠️ openai（未安装，AI 功能不可用）")
        console.print(f"     需要 AI 功能请执行: py -m pip install openai")
    console.print()
    
    # 3. 检查配置
    console.print("[bold]3. 配置检查[/bold]")
    config = load_config()
    
    # 检查 API Key 来源
    env_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if config.get("api_key"):
        masked = config["api_key"][:6] + "****" + config["api_key"][-4:]
        if env_key:
            console.print(f"  ✅ API Key 已配置: {masked} [dim](来自环境变量 OPENAI_API_KEY)[/dim]")
        else:
            console.print(f"  ✅ API Key 已配置: {masked} [dim](来自配置文件)[/dim]")
    else:
        console.print(f"  ❌ API Key 未配置")
        issues.append("API Key 未配置，请执行: lank set")
    
    if config.get("api_base"):
        base_source = ""
        env_base = os.environ.get("OPENAI_API_BASE", "").strip()
        if env_base:
            base_source = " [dim](来自环境变量 OPENAI_API_BASE)[/dim]"
        console.print(f"  ✅ API 地址: {config['api_base']}{base_source}")
    
    if config.get("model"):
        model_source = ""
        env_model = os.environ.get("OPENAI_MODEL", "").strip()
        if env_model:
            model_source = " [dim](来自环境变量 OPENAI_MODEL)[/dim]"
        console.print(f"  ✅ 模型: {config['model']}{model_source}")
    console.print()
    
    # 4. 检查安装方式
    console.print("[bold]4. 安装方式[/bold]")
    # 检查是否通过 pip install 安装
    try:
        from importlib.metadata import distribution, PackageNotFoundError
        try:
            dist = distribution("lank")
            console.print(f"  ✅ 已通过 pip 安装 (版本 {dist.version})")
            console.print(f"     安装路径: {dist.locate_file('') if hasattr(dist, 'locate_file') else 'Python site-packages'}")
        except PackageNotFoundError:
            console.print(f"  ⚠️ 未通过 pip 安装（使用开发模式）")
            console.print(f"     建议执行 'lank install' 安装到系统")
    except ImportError:
        # Python 3.7 及以下兼容
        console.print(f"  ⚠️ 无法检测安装方式")
    console.print()

    
    # 5. 检查 lank 命令是否在 PATH 中
    console.print("[bold]5. 命令可用性[/bold]")
    if sys.platform == "win32":
        import subprocess
        try:
            result = subprocess.run(["where", "lank"], capture_output=True, text=True)
            if result.returncode == 0:
                console.print(f"  ✅ lank 命令在 PATH 中: {result.stdout.strip()}")
            else:
                console.print(f"  ⚠️ lank 命令不在 PATH 中")
                console.print(f"     请执行 'lank install' 或手动添加 PATH")
        except Exception:
            console.print(f"  ⚠️ 无法检测 lank 命令")
    console.print()
    
    # 汇总
    console.print("[bold]📋 诊断结果[/bold]")
    if issues:
        console.print(f"  发现 [bold yellow]{len(issues)}[/bold yellow] 个问题：")
        for i, issue in enumerate(issues, 1):
            console.print(f"  {i}. {issue}")
        console.print()
        console.print("[bold]💡 建议:[/bold] 执行 'lank install' 完成安装，然后 'lank set' 配置 API Key")
    else:
        console.print("  ✅ 一切正常，可以愉快地使用 LANK 了！")
    console.print()
    
    return 0


def cli(argv: Optional[List[str]] = None) -> int:
    """主 CLI 入口"""
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
        initial_question = " ".join(argv[1:]) if len(argv) > 1 else None
        return run_ai_chat(initial_question)

    elif cmd == "set":
        return run_set_command(argv[1:])

    elif cmd == "install":
        return run_install()

    elif cmd == "doctor":
        return run_doctor()

    elif cmd in ("version", "-v", "--version"):
        from . import __version__
        print(f"lank v{__version__}")
        return 0

    else:
        print(f"未知命令: {cmd}")
        print("使用 'lank help' 查看帮助")
        return 2

