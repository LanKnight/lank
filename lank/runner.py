"""
lank/runner.py - 非交互（headless）任务运行器

对应 design.md §5.5 承诺的「非交互模式（单次调用）下自动确认计划、自动通过终审」。
把一整段任务（如 testQuestion 的数模题要求）喂给 AgentLoop，全程无需人工确认，
工具仍受危险命令黑名单约束，产物按提示词规范落盘到工作目录。

用法（CLI）：
    lank run <任务文件或文本> [--cwd DIR]
"""

import os
import sys
from typing import Optional

from .config import set_config, get_config
from .logs import get_logger, setup_logging

logger = get_logger("runner")

# ask_user 在自动模式下的兜底回答：明确告知模型不要等待，基于合理假设继续
_AUTO_ASK_REPLY = (
    "（当前为自动运行模式，无法与用户实时交互。请不要等待用户回复，"
    "基于题目内容与合理假设自行决定并继续推进；缺少的外部数据可给出假设值并在文档中注明。）"
)


def _load_task_text(task_arg: str) -> str:
    """task_arg 若为存在的文件则读其内容，否则视为直接给出的任务文本。"""
    if os.path.isfile(task_arg):
        with open(task_arg, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    return task_arg


def _build_callbacks(console):
    """构建一套 headless 回调：自动放行工具、自动确认计划与终审、进度打印到 stdout。"""
    from .agent import AgentCallbacks
    from .agent.types import render_plan_text, StepStatus

    def on_text(text: str) -> None:
        # 流式增量直接打印，保持与交互式一致的实时反馈
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
        except Exception:
            pass

    def on_tool_call(name, args, result=None):
        import json as _json
        if result is None:
            # 自动放行；execute_command 的危险命令拦截在工具内部兜底
            arg_str = _json.dumps(args, ensure_ascii=False)
            if len(arg_str) > 200:
                arg_str = arg_str[:200] + "…"
            console.print(f"[dim]🔧 调用工具 {name}: {arg_str}[/dim]")
            return True
        r = str(result)
        if len(r) > 400:
            r = r[:400] + "…"
        console.print(f"[dim yellow]   ↳ {r}[/dim yellow]")
        return True

    def on_plan_render(plan):
        console.print("[bold cyan]📋 执行计划:[/bold cyan]")
        console.print(render_plan_text(plan))

    def on_plan_confirm(plan):
        return True  # 非交互模式自动确认

    def on_step_progress(step, phase):
        if phase == "start":
            console.print(f"\n[bold]⏳ [步骤 {step.id}] {step.title}[/bold]")
        else:
            icon = {StepStatus.DONE: "✅", StepStatus.BLOCKED: "⛔"}.get(step.status, "⏳")
            console.print(f"{icon} [步骤 {step.id}] {step.title} 结束：{(step.summary or '')[:120]}")

    def on_review(verdict):
        if verdict.deliverable:
            console.print("[bold green]✅ 审核通过，可交付[/bold green]")
        else:
            console.print("[bold yellow]⚠️ 审核未达标，补充步骤重跑：[/bold yellow]")
            for issue in verdict.issues[:8]:
                console.print(f"   - {issue}")

    def on_review_confirm(verdict):
        return True  # 非交互模式自动通过终审

    def on_ask_user(question, options):
        console.print(f"[dim]❓ (自动应答) {question}[/dim]")
        return _AUTO_ASK_REPLY

    return AgentCallbacks(
        on_text=on_text,
        on_tool_call=on_tool_call,
        on_plan_render=on_plan_render,
        on_plan_confirm=on_plan_confirm,
        on_step_progress=on_step_progress,
        on_review=on_review,
        on_review_confirm=on_review_confirm,
        on_ask_user=on_ask_user,
    )


def run_task(task_arg: str, cwd: Optional[str] = None) -> int:
    """非交互执行一整段任务。

    Args:
        task_arg: 任务文件路径或直接的任务文本
        cwd: 工作目录（Agent 的读写/命令都在此目录下进行）

    Returns:
        进程退出码（0 成功交付）
    """
    setup_logging()
    from rich.console import Console

    # Windows 控制台默认 GBK，模型输出/日志中的 emoji 与非 GBK 字符会抛
    # UnicodeEncodeError；先把标准流重配为 UTF-8（写入失败降级替换）。
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # 子进程（Agent 运行的 Python 脚本）统一以 UTF-8 输出，避免中文乱码/解码崩溃
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")

    console = Console()

    # 切工作目录（决定 write_to_file / execute_command 的落点）
    if cwd:
        if not os.path.isdir(cwd):
            console.print(f"[red]❌ 工作目录不存在: {cwd}[/red]")
            return 2
        os.chdir(cwd)
    working_dir = os.getcwd()
    console.print(f"[bold]📂 工作目录:[/bold] {working_dir}")

    task_text = _load_task_text(task_arg)
    if not task_text.strip():
        console.print("[red]❌ 任务内容为空[/red]")
        return 2

    # 长任务调优：对工具/命令输出与轮数封顶（省 token），保留足够的 max_tokens/cmd_timeout
    _tune_for_long_task()

    try:
        from .ai_client import AIClient
    except ImportError:
        console.print("[red]❌ 缺少 openai 库，请执行: pip install openai[/red]")
        return 1

    client = AIClient()
    ready, msg = client.is_ready()
    if not ready:
        console.print(f"[red]❌ {msg}[/red]")
        return 1

    from .agent import AgentLoop
    try:
        from .memory import get_relevant_context
        memory_text = get_relevant_context(task_text[:200])
    except Exception:
        memory_text = ""

    loop = AgentLoop(client, _build_callbacks(console))
    console.print("[bold]🚀 开始执行任务（自动模式，全程无需确认）...[/bold]\n")
    result = loop.run(task_text, memory_text=memory_text, history=[])

    console.print("\n[bold cyan]════════════ 最终交付 ════════════[/bold cyan]")
    console.print(result.response or "（无输出）")

    # 列出工作目录里新产出的文件，方便核对
    _list_outputs(console, working_dir)

    # 本任务 token 用量（可观测成本）：仅打印本次摘要
    # （逐次用量已由 AIClient 在每次响应时增量落盘到 stats.json，此处不再累加以免重复计数）
    try:
        console.print(f"\n[bold]📊 本次用量:[/bold] {client.usage_summary()}")
    except Exception:
        pass

    if not result.success:
        console.print("[yellow]⚠️ 任务未完全成功（详见上方审核结论）[/yellow]")
        return 1
    return 0


def _tune_for_long_task() -> None:
    """为长任务调优：对“token 大户”设上限，对“交付长度/重脚本耗时”设下限。

    上轮实测：把输出上限/工具轮数调大会让每步每轮回灌几十 KB → token 与耗时
    爆炸。改为反向：工具/命令输出封顶精简，轮数与步数封顶，但保留足够的
    max_tokens（交付物需要长）与 cmd_timeout（matplotlib/pandas 脚本需要时间）。
    """
    floors = {          # 至少这么高（交付/性能需要）
        "max_tokens": 8192,
        "cmd_timeout": 150,
    }
    ceilings = {        # 至多这么高（省 token / 提速）
        "tool_output_limit": 4096,
        "cmd_output_limit": 6144,
        "max_tool_rounds": 30,
        "max_plan_steps": 10,
        "max_review_rounds": 2,
    }
    for key, want in floors.items():
        try:
            cur = int(get_config(key, 0))
        except (TypeError, ValueError):
            cur = 0
        if cur < want:
            set_config(key, want)
            logger.info("run 模式提高 %s: %s → %s", key, cur, want)
    for key, cap in ceilings.items():
        try:
            cur = int(get_config(key, cap))
        except (TypeError, ValueError):
            cur = cap
        if cur > cap:
            set_config(key, cap)
            logger.info("run 模式收紧 %s: %s → %s", key, cur, cap)


def _list_outputs(console, working_dir: str) -> None:
    """列出工作目录下生成的交付文件（md/png/csv/py），便于核对完成情况。"""
    exts = {".md", ".png", ".jpg", ".csv", ".py"}
    found = []
    for root, dirs, files in os.walk(working_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
        # 跳过源码包目录本身，聚焦运行产物
        if os.path.basename(root) in {"lank", "tests", "docs"}:
            continue
        for fn in files:
            if os.path.splitext(fn)[1].lower() in exts:
                found.append(os.path.relpath(os.path.join(root, fn), working_dir))
    if found:
        console.print("\n[bold]📦 工作目录产物:[/bold]")
        for p in sorted(found):
            console.print(f"   • {p}")
