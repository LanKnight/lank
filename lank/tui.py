"""
TUI 聊天界面模块
支持普通聊天模式和 AI 智能模式
"""

import json
import sys
import time
from typing import Any, Dict, List, Tuple

from .config import load_config, get_config, set_config
from .memory import save_conversation
from .utils import get_theme

# Rich 导入
from rich.console import Console

# Prompt toolkit
try:
    from prompt_toolkit import prompt
    from prompt_toolkit.history import InMemoryHistory
    from prompt_toolkit.formatted_text import HTML
except ImportError:
    prompt = input  # type: ignore
    InMemoryHistory = None  # type: ignore
    HTML = None  # type: ignore


# 常量
FIXED_REPLY = "这个问题很不错，建议问AI"


def stream_text(console: Console, text: str, speed: float = 0.03):
    """模拟流式输出效果"""
    from rich.text import Text

    output_text = Text()
    for char in text:
        output_text.append(char, style="bold magenta")
        console.print(output_text, end="\r")
        time.sleep(speed)
    console.print()


def render_chat(console: Console, messages: List[Tuple[str, str]]):
    """渲染聊天界面 — 简洁无边框，消息直接堆叠"""
    theme = get_theme()

    if not messages:
        console.print(f"[dim](开始新的对话...)[/dim]")
        return

    for role, text in messages:
        if role == "user":
            console.print(
                f"[bold {theme['user_color']}]▸ 你:[/bold {theme['user_color']}] {text}"
            )
        elif role == "assistant":
            console.print(
                f"[bold {theme['ai_color']}]▸ AI:[/bold {theme['ai_color']}] {text}"
            )
        else:  # system
            console.print(f"[dim {theme['system_color']}]⚙ {text}[/dim {theme['system_color']}]")
        console.print()


def run_tui():
    """运行 TUI 聊天界面"""
    console = Console()
    messages: List[Tuple[str, str]] = [("system", "欢迎使用 LANK AI — 输入 /help 查看帮助")]

    history = InMemoryHistory() if InMemoryHistory is not None else None

    # 简洁欢迎信息
    console.print("[bold cyan]LANK AI[/bold cyan] [dim]v0.2.0 — 智能终端助手[/dim]")
    console.print("[dim]输入 /ai 切换 AI 模式 | /help 查看帮助 | exit 退出[/dim]\n")

    # 初始化 AI 客户端（整个会话复用一个实例）
    client = None
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
    tool_count = 0

    try:
        while True:
            try:
                console.clear()
                render_chat(console, messages)

                # 模式指示
                theme = get_theme()
                if HTML is not None:
                    mode_color = theme["ai_color"] if ai_mode else "cyan"
                    mode_label = "🤖 AI" if ai_mode else "💬 普通"
                    mode_html = f"<{mode_color}>{mode_label}</{mode_color}>"
                    prompt_text = HTML(f"\n[{mode_html}] ")
                else:
                    mode_text = "🤖 AI" if ai_mode else "💬 普通"
                    prompt_text = f"\n[{mode_text}] "

                if history is not None:
                    user_input = prompt(prompt_text, history=history)
                else:
                    user_input = prompt(prompt_text)
            except (EOFError, KeyboardInterrupt):
                console.print("\n[bold green]感谢使用 LANK AI！再见![/bold green]")
                break

            if not user_input:
                continue

            # 处理退出
            if user_input.strip().lower() in ("exit", "quit"):
                console.print("\n[bold green]感谢使用 LANK AI！祝您有美好的一天![/bold green]")
                break

            # 处理命令
            if user_input.strip().startswith("/"):
                cmd_parts = user_input.strip().split(maxsplit=1)
                cmd = cmd_parts[0].lower()
                cmd_arg = cmd_parts[1] if len(cmd_parts) > 1 else ""

                if cmd == "/ai":
                    if ai_available:
                        ai_mode = True
                        messages.append(("system", "已切换到 AI 智能模式"))
                    else:
                        messages.append(("system", "⚠️ AI 模式不可用，请先配置 API Key (lank set)"))
                    continue

                elif cmd == "/normal":
                    ai_mode = False
                    messages.append(("system", "已切换到普通聊天模式"))
                    continue

                elif cmd == "/help":
                    messages.append(("system", """
可用命令:
  /ai       切换到 AI 智能模式（需配置 API Key）
  /normal   切换到普通聊天模式
  /help     显示此帮助
  /clear    清空对话
  /save     保存对话
  /export   导出对话 (markdown/json)
  /stats    显示使用统计
  /theme    显示 / 切换主题 (/theme cyberpunk)
  /model    显示 / 切换模型 (/model deepseek-v4-pro)
  /todo     管理待办 (/todo add 任务 | /todo list | /todo done 编号)
  /update   检查更新
  exit      退出程序
                    """.strip()))
                    continue

                elif cmd == "/clear":
                    messages = [("system", "对话已清空")]
                    ai_history = []
                    continue

                elif cmd == "/save":
                    if ai_history:
                        session_id = save_conversation(ai_history)
                        messages.append(("system", f"✅ 对话已保存 (ID: {session_id})"))
                    else:
                        messages.append(("system", "⚠️ 没有可保存的对话"))
                    continue

                elif cmd == "/export":
                    try:
                        from .utils import export_conversation
                    except ImportError:
                        messages.append(("system", "⚠️ 导出功能不可用"))
                        continue
                    data = ai_history if ai_history else [
                        {"role": role, "content": text} for role, text in messages
                    ]
                    fmt = "json" if cmd_arg.lower() == "json" else "markdown"
                    path = export_conversation(data, format=fmt)
                    if path:
                        messages.append(("system", f"✅ 已导出: {path}"))
                    else:
                        messages.append(("system", "⚠️ 没有可导出的内容"))
                    continue

                elif cmd == "/update":
                    try:
                        from .utils import check_for_updates

                        result = check_for_updates()
                        messages.append(("system", result))
                    except Exception:
                        messages.append(("system", "⚠️ 无法检查更新"))
                    continue

                elif cmd == "/stats":
                    try:
                        from .utils import get_stats_summary

                        messages.append(("system", f"\n{get_stats_summary()}"))
                    except Exception:
                        messages.append(("system", "⚠️ 无法获取统计"))
                    continue

                elif cmd == "/theme":
                    try:
                        from .utils import list_themes, THEMES

                        if cmd_arg and cmd_arg in THEMES:
                            set_config("theme", cmd_arg)
                            messages.append(("system", f"✅ 主题已切换为: {cmd_arg}"))
                        else:
                            messages.append(("system", f"\n{list_themes()}"))
                    except Exception:
                        messages.append(("system", "⚠️ 主题切换失败"))
                    continue

                elif cmd == "/model":
                    try:
                        from .model_config import list_available_models

                        if cmd_arg:
                            set_config("model", cmd_arg)
                            if client:
                                client.set_model(cmd_arg)
                            messages.append(("system", f"✅ 已切换模型: {cmd_arg}"))
                        else:
                            current = get_config("model", "deepseek-v4-flash")
                            lines = [f"当前模型: [bold]{current}[/bold]", "", "可用模型:"]
                            for m in list_available_models():
                                lines.append(f"  {m['id']} — {m['name']}: {m['description']}")
                            messages.append(("system", "\n".join(lines)))
                    except Exception:
                        messages.append(("system", "⚠️ 模型切换失败"))
                    continue

                elif cmd == "/todo":
                    try:
                        from .tools.todo_tools import todo_add, todo_list, todo_done, todo_delete

                        sub_parts = cmd_arg.split(maxsplit=1)
                        sub = sub_parts[0].lower() if sub_parts else "list"
                        sub_arg = sub_parts[1] if len(sub_parts) > 1 else ""

                        if sub == "list":
                            result = todo_list()
                        elif sub == "add" and sub_arg:
                            result = todo_add(sub_arg)
                        elif sub == "done" and sub_arg:
                            try:
                                result = todo_done(int(sub_arg))
                            except ValueError:
                                result = "⚠️ 待办 ID 必须是数字"
                        elif sub in ("del", "delete") and sub_arg:
                            try:
                                result = todo_delete(int(sub_arg))
                            except ValueError:
                                result = "⚠️ 待办 ID 必须是数字"
                        else:
                            result = "用法: /todo [list|add 任务|done 编号|del 编号]"
                        messages.append(("system", result))
                    except Exception:
                        messages.append(("system", "⚠️ 待办操作失败"))
                    continue

                else:
                    messages.append(("system", f"未知命令: {cmd}，输入 /help 查看帮助"))
                    continue

            messages.append(("user", user_input.strip()))

            if ai_mode and ai_available and client is not None:
                # AI 模式
                try:
                    ai_history.append({"role": "user", "content": user_input.strip()})

                    # 流式积累文本
                    streamed_parts = []

                    def on_tool_call(name, args, result=None):
                        nonlocal tool_count
                        if result is None:
                            console.print(f"\n[bold yellow]🔧 AI 想要调用工具: {name}[/bold yellow]")
                            console.print(f"   参数: {json.dumps(args, ensure_ascii=False)}")
                            console.print("[bold]   是否允许? [Y/n]: [/bold]", end="")
                            ans = input().strip().lower()
                            return ans not in ("n", "no")
                        else:
                            tool_count += 1
                            console.print(f"\n[bold cyan]🔧 工具 [{name}] 执行结果:[/bold cyan]")
                            result_str = str(result)
                            if len(result_str) > 300:
                                result_str = result_str[:300] + "..."
                            console.print(f"   {result_str}")
                            return True

                    def on_text(text):
                        streamed_parts.append(text)
                        console.print(text, style=f"bold {theme['ai_color']}", end="")

                    console.print(f"  [bold {theme['ai_color']}]▸ AI: [/bold {theme['ai_color']}]", end="")
                    success, response, ai_history = client.chat(
                        messages=ai_history,
                        stream=True,
                        on_tool_call=on_tool_call,
                        on_text=on_text,
                    )
                    console.print()  # 流式后换行

                    if success:
                        messages.append(("assistant", "".join(streamed_parts) or response))
                    else:
                        messages.append(("system", f"⚠️ {response}"))

                    # 保存对话
                    if ai_history:
                        save_conversation(ai_history)

                except Exception as e:
                    messages.append(("system", f"⚠️ AI 调用失败: {e}"))
            else:
                # 普通模式 - 固定回复
                console.print(f"\n[bold {theme['ai_color']}]▸ AI 助手:[/bold {theme['ai_color']}] ", end="")
                stream_text(console, FIXED_REPLY, speed=0.02)
                messages.append(("assistant", FIXED_REPLY))

    finally:
        # 记录会话统计
        try:
            from .utils import record_session

            msg_count = sum(1 for r, _ in messages if r in ("user", "assistant"))
            record_session(msg_count, tool_count)
        except Exception:
            pass
