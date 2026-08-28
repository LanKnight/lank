"""
TUI 全屏聊天界面 - 输入框固定底部，消息内容向上滚动（可回看）

设计（todo.md 需求：输入框一直放下面，其他内容往上面堆）：
  - prompt_toolkit 全屏应用：消息区 + 底部固定输入框
  - 消息区自动滚动到底，PageUp/PageDown 回看历史
  - 普通模式 / AI 模式（ReAct 框架 AgentLoop，后台线程执行）
  - 工具确认 / 提问通过线程事件桥接（UI 线程 ↔ AI 线程）
"""

import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .config import get_config, set_config
from .logs import setup_logging
from .utils import trim_history

setup_logging()

FIXED_REPLY = "这个问题很不错，建议问AI"

# rich 颜色名 → prompt_toolkit 颜色（全屏 TUI 主题映射）
_RICH_TO_PT_COLOR = {
    "cyan": "#00afff", "magenta": "#ff5faf", "green": "#5fd700",
    "light_cyan": "#87d7ff", "light_magenta": "#ff87d7", "light_green": "#87ff5f",
    "bright_cyan": "#00ffff", "bright_magenta": "#ff00ff", "bright_green": "#00ff00",
    "bright_yellow": "#ffff00", "bright_red": "#ff0000",
    "blue": "#005faf", "purple": "#af5fff", "gold": "#d7af00", "gold1": "#d7af00",
    "orange1": "#ff8700", "hot_pink": "#ff5f87", "light_sky_blue": "#87afff",
    "dark_green": "#005f00", "yellow": "#d7d700", "red": "#ff0000",
}

try:
    from prompt_toolkit.application import Application
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.history import InMemoryHistory
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import HSplit, Layout, VSplit, Window
    from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
    from prompt_toolkit.layout.dimension import Dimension as Dim
    from prompt_toolkit.styles import Style
    PT_AVAILABLE = True
except ImportError:
    PT_AVAILABLE = False


class ChatApp:
    """全屏聊天应用：消息区（可回看）+ 底部固定输入框

    Args:
        ai_only: True = 启动即 AI 模式（lank ai）；False = 可切换普通/AI（lank tui）
        initial_question: 启动时自动发送的初始问题
        client: 可注入的 AIClient（由 cli 传入时复用）
    """

    def __init__(self, ai_only: bool = False, initial_question: Optional[str] = None,
                 client=None):
        self.ai_only = ai_only
        self.initial_question = initial_question
        self.client = client
        self.messages: List[Tuple[str, str]] = []      # (role, text)
        self.ai_mode = ai_only
        self.ai_history: List[Dict[str, Any]] = []
        self.tool_count = 0
        self.session_id: Optional[str] = None
        self.ai_available = False
        self._streamed_parts: List[str] = []
        self._static_items_cache = None   # 消息区静态渲染片段缓存（防每帧重建）
        self._static_items_key = None
        self._pending_ask: Optional[Dict[str, Any]] = None  # 待回答的交互
        self._back_lines = 0      # 回看行数（0=底部），PageUp/PageDown 调整
        self._ai_running = False  # 单一 AI 运行互斥（防止并发线程踩踏）
        self._finalized_sessions = set()  # 已做过会话总结的 session（防重复 LLM 调用）
        self._last_stream_invalidate = 0.0  # 流式输出节流：上次刷新时间戳
        self._lock = threading.Lock()

        # prompt_toolkit 组件（PT_AVAILABLE 时创建）
        self.app: Optional[Application] = None
        self.message_window: Optional[Window] = None
        self.input_buffer: Optional[Buffer] = None
        self.layout = None
        self._pt_ok = PT_AVAILABLE

    # ═══════════════ 初始化 ═══════════════

    def _setup_client(self) -> bool:
        """初始化 AI 客户端；返回是否可用"""
        if self.client is not None:
            self.ai_available = True
            return True
        try:
            from .ai_client import AIClient
            self.client = AIClient()
            ready, _ = self.client.is_ready()
            self.ai_available = ready
            return ready
        except Exception:
            self.ai_available = False
            return False

    # ═══════════════ 渲染 ═══════════════

    def _static_messages_items(self) -> List[Tuple[str, str]]:
        """消息区静态片段（不含流式）——按内容指纹缓存，避免每帧重建全部消息"""
        key = (len(self.messages),
               self.messages[-1][1][:40] if self.messages else "",
               self.messages[-1][0] if self.messages else "")
        if self._static_items_cache is not None and self._static_items_key == key:
            return self._static_items_cache
        items: List[Tuple[str, str]] = []
        for role, text in self.messages:
            if role == "user":
                items.append(("class:chat.user", f"▸ 你: {text}\n\n"))
            elif role == "assistant":
                items.append(("class:chat.ai", f"▸ AI: {text}\n\n"))
            elif role == "tool":
                items.append(("class:chat.tool", f"🔧 {str(text)[:300]}\n\n"))
            else:
                items.append(("class:chat.sys", f"⚙ {text}\n\n"))
        self._static_items_cache = items
        self._static_items_key = key
        return items

    def _build_render_items(self) -> List[Tuple[str, str]]:
        """构建消息区渲染片段（不持锁，由调用方在锁内调用）"""
        items = self._static_messages_items()
        if self._streamed_parts:
            items = list(items) + [("class:chat.ai", f"▸ AI: {''.join(self._streamed_parts)}")]
        elif not self.messages:
            items = [("class:chat.sys",
                      "欢迎使用 LANK — 输入 /help 查看帮助\n"
                      "输入框固定在底部，PageUp/PageDown 回看历史\n"
                      "/history 查看历史会话 | /resume <ID> 恢复")]
        return items

    def _render_line_count(self) -> int:
        """当前渲染逻辑行数（调用方需持锁）"""
        from prompt_toolkit.formatted_text import FormattedText
        from prompt_toolkit.formatted_text.utils import split_lines
        return len(list(split_lines(FormattedText(self._build_render_items()))))

    def _get_cursor_position(self):
        """滚动锚点：用与渲染完全相同的 split_lines 行数计算，保证永不越界"""
        from prompt_toolkit.data_structures import Point
        from prompt_toolkit.formatted_text import FormattedText
        from prompt_toolkit.formatted_text.utils import split_lines
        with self._lock:
            ft = FormattedText(self._build_render_items())
            n_lines = len(list(split_lines(ft)))
            anchor = max(0, n_lines - 1 - self._back_lines)
            anchor = min(anchor, max(0, n_lines - 1))  # 双保险 clamp
        return Point(x=0, y=anchor)

    def _render_messages(self):
        """消息区渲染（每次刷新调用）"""
        from prompt_toolkit.formatted_text import FormattedText
        with self._lock:
            return FormattedText(self._build_render_items())

    def _left_prompt(self):
        """输入框左侧模式提示"""
        from prompt_toolkit.formatted_text import FormattedText
        if self._pending_ask is not None:
            return FormattedText([("class:chat.sys", ">> ")])
        mode = "🤖 AI" if self.ai_mode else "💬 普通"
        return FormattedText([("class:chat.sys", f"[{mode}] ")])

    def _scroll_to_bottom(self) -> None:
        """回到消息区底部（重置回看位置）"""
        self._back_lines = 0

    def _add_message(self, role: str, text: str) -> None:
        """追加一条消息并刷新

        回看位置保持：用户正在回看历史（_back_lines > 0）时不被新消息拉回底部；
        位于底部时锚点自动跟随最后一行。
        """
        with self._lock:
            self.messages.append((role, text))
        self._invalidate()

    def _invalidate(self) -> None:
        """刷新界面（线程安全，AI 后台线程可调用）"""
        if self.app is not None:
            self.app.invalidate()

    # ═══════════════ 交互桥接（AI 线程 → UI 线程） ═══════════════

    def _ask_sync(self, prompt_text: str, responder: Callable[[str], None],
                  timeout: float = 300.0) -> None:
        """投递问题给 UI，阻塞等待用户回答（AI 线程调用）

        带超时防止永久阻塞（用户退出/异常时 300s 后放弃）。
        """
        evt = threading.Event()

        def callback(answer: str) -> None:
            responder(answer)
            evt.set()

        with self._lock:
            self._pending_ask = {"callback": callback}
        self._add_message("system", f"❓ {prompt_text}")
        evt.wait(timeout)  # 阻塞直到 UI 线程回答（或超时）

    def confirm_sync(self, question: str) -> bool:
        """确认交互（AI 线程调用）；空输入/非确认词一律视为拒绝（安全默认）"""
        result = {"ok": False}

        def responder(answer: str) -> None:
            ans = answer.strip().lower()
            result["ok"] = ans in ("y", "yes", "是", "ok")

        self._ask_sync(question, responder)
        return result["ok"]

    def ask_user_sync(self, question: str, options: Optional[List[str]] = None) -> str:
        """提问交互（AI 线程调用）"""
        result = {"answer": ""}
        opt_text = "  ".join(f"{i + 1}. {o}" for i, o in enumerate(options or []))
        if opt_text:
            question = f"{question}（{opt_text}）"

        def responder(answer: str) -> None:
            result["answer"] = answer.strip()

        self._ask_sync(question, responder)
        return result["answer"]

    # ═══════════════ AI 处理（后台线程） ═══════════════

    def _build_callbacks(self):
        from .agent import AgentCallbacks

        def on_text(text: str) -> None:
            # 只 append 片段，渲染时 join（避免逐 token 字符串累加的 O(n²)）；
            # 渲染节流：最多每 50ms 刷新一次，长回复显著降 CPU，最终由消息追加补齐
            with self._lock:
                self._streamed_parts.append(text)
            now = time.monotonic()
            if now - self._last_stream_invalidate >= 0.05:
                self._last_stream_invalidate = now
                self._invalidate()

        def on_tool_call(name, args, result=None):
            if result is None:
                import json as _json
                arg_str = _json.dumps(args, ensure_ascii=False)
                question = (f"AI 想要调用工具 [{name}]，参数: {arg_str}\n"
                            f"是否允许? (y=是 / n=否 / a=总是允许)")
                ans = {"val": ""}
                self._ask_sync(question, lambda a: ans.update(val=a.strip().lower()))
                v = ans["val"]
                # 白名单式判定：只有明确的 y/yes/是/a 放行；空回车/超时/乱输一律拒绝（安全默认）
                if v == "a":
                    try:
                        from .tools import allow_forever
                        hint = str(args.get("command", "")) if name == "execute_command" else ""
                        allow_forever(name, hint)
                    except Exception:
                        pass
                    self._add_message("system", f"🔧 正在执行工具: {name}")
                    return True
                if v in ("y", "yes", "是", "ok"):
                    self._add_message("system", f"🔧 正在执行工具: {name}")
                    return True
                return False
            else:
                with self._lock:
                    self.tool_count += 1
                self._add_message("tool", str(result))
                return True

        def on_plan_render(plan):
            from .agent.types import render_plan_text
            self._add_message("system", "📋 AI 的执行计划:\n" + render_plan_text(plan))

        def on_plan_confirm(plan):
            return self.confirm_sync("是否按此计划执行? (y/n)")

        def on_review(verdict):
            if verdict.deliverable:
                self._add_message("system", "✅ 审核通过，可以交付")
            else:
                self._add_message("system", "⚠️ 审核未达标，补充执行:")
                for issue in verdict.issues[:5]:
                    self._add_message("system", f"  - {issue}")

        def on_ask_user(question, options):
            return self.ask_user_sync(question, options)

        def on_step_progress(step, phase):
            from .agent.types import StepStatus
            if phase == "start":
                # 步骤开始：清空流式残留，显示进度
                with self._lock:
                    self._streamed_parts = []
                self._add_message("system", f"⏳ [步骤 {step.id}] {step.title} ...")
            else:
                if step.status == StepStatus.DONE:
                    self._add_message("system", f"✅ [步骤 {step.id}] {step.title} 完成")
                elif step.status == StepStatus.BLOCKED:
                    self._add_message("system",
                                      f"⛔ [步骤 {step.id}] {step.title} 受阻: {step.summary[:80]}")

        def on_review_confirm(verdict):
            # 用户终审：可交付时让用户确认交付（/auto 模式自动通过）
            if get_config("auto_mode", False):
                return True
            return self.confirm_sync("交付结果是否满意? (y=是 / n=否)")

        return AgentCallbacks(
            on_text=on_text,
            on_tool_call=on_tool_call,
            on_plan_render=on_plan_render,
            on_plan_confirm=on_plan_confirm,
            on_review=on_review,
            on_review_confirm=on_review_confirm,
            on_ask_user=on_ask_user,
            on_step_progress=on_step_progress,
        )

    def _run_ai(self, user_input: str) -> None:
        """后台线程：执行 AgentLoop（plan→act→review）"""
        try:
            from .agent import AgentLoop
            from .memory import get_relevant_context

            loop = AgentLoop(self.client, self._build_callbacks())
            try:
                memory_text = get_relevant_context(user_input)
            except Exception:
                memory_text = ""

            with self._lock:
                self._streamed_parts = []

            result = loop.run(user_input, memory_text=memory_text)

            with self._lock:
                if result.plan is None:
                    # 简单问答：用流式拼接的完整回答
                    full = "".join(self._streamed_parts) or result.response
                else:
                    # 复杂任务：用审核后的交付总结（不拼接执行过程碎片）
                    full = result.response or "（任务执行完成）"
                self._streamed_parts = []

            if result.success:
                self._add_message("assistant", full)
                with self._lock:
                    self.ai_history.append({"role": "assistant", "content": full})
            else:
                self._add_message("system", f"⚠️ {result.response}")
                # 终审驳回等 REVIEW 阶段失败：交付文本也进历史，避免上下文断裂
                if result.phase.value == "review":
                    with self._lock:
                        self.ai_history.append({"role": "assistant", "content": result.response})

            # 保存会话（会话内复用 session_id）+ 长会话增量滚动总结
            try:
                from .memory import save_conversation, needs_rollup, finalize_session
                if self.ai_history:
                    sid = save_conversation(self.ai_history, session_id=self.session_id)
                    if sid:
                        self.session_id = sid
                    if self.session_id and self.session_id not in self._finalized_sessions \
                            and needs_rollup(self.ai_history):
                        self._finalized_sessions.add(self.session_id)
                        threading.Thread(
                            target=finalize_session,
                            args=(self.session_id, self.ai_history),
                            daemon=True,
                        ).start()
            except Exception:
                pass
        except Exception as e:
            with self._lock:
                self._streamed_parts = []  # 失败路径也清残留
            self._add_message("system", f"⚠️ AI 调用失败: {e}")
        finally:
            with self._lock:
                self._ai_running = False
            self._invalidate()

    # ═══════════════ 输入处理（UI 线程） ═══════════════

    def _handle_input(self, text: str) -> None:
        """处理一条用户输入（命令 / 普通 / AI）"""
        if not text or not text.strip():
            return
        text = text.strip()

        if text.lower() in ("exit", "quit"):
            if self.app is not None:
                self.app.exit()
            return

        if text.startswith("/"):
            self._handle_command(text)
            return

        self._add_message("user", text)

        if self.ai_mode and self.ai_available and self.client is not None:
            with self._lock:
                if self._ai_running:
                    # 上一轮 AI 任务还在执行，拒绝并发提交（防线程踩踏）
                    self.messages.append(("system", "⚠️ 上一条任务还在执行中，请稍候（Ctrl+C 可中断）"))
                    self._back_lines = 0
                    self._invalidate()
                    return
                self._ai_running = True
                self.ai_history.append({"role": "user", "content": text})
                self.ai_history = trim_history(self.ai_history)
            threading.Thread(target=self._run_ai, args=(text,), daemon=True).start()
        else:
            if self.ai_mode and not self.ai_available:
                self._add_message("system", "⚠️ AI 模式不可用，请先配置 API Key (lank set)")
            else:
                # 普通模式：打字效果放后台线程，不阻塞输入
                threading.Thread(target=self._stream_reply,
                                 args=(FIXED_REPLY,), daemon=True).start()

    def _stream_reply(self, text: str) -> None:
        """普通模式：模拟流式打字效果"""
        with self._lock:
            self._streamed_parts = []
        for ch in text:
            with self._lock:
                self._streamed_parts.append(ch)
            self._invalidate()
            time.sleep(0.02)
        with self._lock:
            self._streamed_parts = []
        self._add_message("assistant", text)

    def _handle_command(self, text: str) -> None:
        """处理 /命令，输出追加到消息区"""
        cmd_parts = text.split(maxsplit=1)
        cmd = cmd_parts[0].lower()
        cmd_arg = cmd_parts[1] if len(cmd_parts) > 1 else ""
        out: List[str] = []

        if cmd == "/ai":
            if self.ai_available:
                self.ai_mode = True
                out.append("已切换到 AI 智能模式")
            else:
                out.append("⚠️ AI 模式不可用，请先配置 API Key (lank set)")
        elif cmd == "/normal":
            self.ai_mode = False
            out.append("已切换到普通聊天模式")
        elif cmd == "/auto":
            new_val = not get_config("auto_mode", False)
            if set_config("auto_mode", new_val):
                out.append(f"自动模式已{'开启' if new_val else '关闭'}（计划自动确认、审核自动通过）")
            else:
                out.append("⚠️ 自动模式保存失败")
        elif cmd == "/clear":
            with self._lock:
                if self._ai_running:
                    self.messages.append(("system", "⚠️ 任务执行中，请先等待完成（Ctrl+C 可中断）"))
                    self._back_lines = 0
                    self._invalidate()
                    return
                self.messages = [("system", "对话已清空")]
                self.ai_history = []
                self.session_id = None  # 清空后开新会话，避免旧 id 覆盖写入
                self._streamed_parts = []
            self._back_lines = 0
            self._invalidate()
            return
        elif cmd == "/history":
            try:
                from .memory import list_sessions, load_summaries
                sessions = list_sessions(7)
                if not sessions:
                    out.append("暂无历史会话")
                else:
                    summaries = load_summaries()
                    out.append(f"最近会话（共 {len(sessions)} 个，/resume <ID> 恢复）:")
                    for s in sessions[:10]:
                        sid = s["session_id"]
                        summ = summaries.get(sid, {}).get("summary", "")[:45]
                        out.append(f"  {sid}  [{s['message_count']}条] {summ}")
            except Exception:
                out.append("无法读取历史")
        elif cmd == "/resume":
            try:
                with self._lock:
                    if self._ai_running:
                        self.messages.append(("system", "⚠️ 任务执行中，请先等待完成再恢复会话"))
                        self._invalidate()
                        return
                from .memory import load_conversation
                sid = cmd_arg.strip()
                msgs = load_conversation(sid) if sid else None
                if not msgs:
                    out.append("未找到会话，用 /history 查看列表")
                else:
                    with self._lock:
                        self.messages = [
                            (m.get("role", ""), str(m.get("content", "")))
                            for m in msgs
                            if m.get("role") in ("user", "assistant", "system", "tool")
                        ]
                        self.ai_history = [
                            dict(m) for m in msgs if m.get("role") in ("user", "assistant")
                        ]
                        self.session_id = sid
                        self._streamed_parts = []
                    self._back_lines = 0
                    out.append(f"已恢复会话 {sid}（{len(msgs)} 条消息），可继续对话")
            except Exception:
                out.append("恢复失败")
        elif cmd == "/help":
            out.append("""可用命令:
  /ai       切换到 AI 智能模式
  /normal   切换到普通聊天模式
  /auto     切换自动模式（计划自动确认、审核自动通过）
  /clear    清空对话
  /save     保存对话
  /history  查看历史会话
  /resume   <ID> 恢复历史会话（回滚到之前的聊天记录）
  /export   [json] 导出对话
  /stats    使用统计
  /theme    [名称] 切换主题
  /model    [名称] 切换模型
  /todo     list|add 任务|done 编号|del 编号
  /update   检查更新
  exit      退出程序
  PageUp/PageDown  回看历史消息
  Ctrl+Home/Ctrl+End 跳顶部/底部""")
        elif cmd == "/save":
            from .memory import save_conversation
            if self.ai_history:
                sid = save_conversation(self.ai_history, session_id=self.session_id)
                if sid:
                    self.session_id = sid
                out.append(f"对话已保存 (ID: {sid})")
            else:
                out.append("没有可保存的对话")
        elif cmd == "/stats":
            try:
                from .utils import get_stats_summary
                out.append(get_stats_summary())
            except Exception:
                out.append("无法获取统计")
        elif cmd == "/theme":
            try:
                from .utils import list_themes, THEMES
                if cmd_arg and cmd_arg in THEMES:
                    set_config("theme", cmd_arg)
                    self._build_style()  # 全屏 TUI 重新应用主题配色
                    out.append(f"主题已切换为: {cmd_arg}")
                else:
                    out.append(list_themes())
            except Exception:
                out.append("主题切换失败")
        elif cmd == "/model":
            try:
                from .model_config import list_available_models
                if cmd_arg:
                    ok = set_config("model", cmd_arg)
                    if self.client is not None:
                        self.client.set_model(cmd_arg)
                    out.append(f"已切换模型: {cmd_arg}" if ok else "⚠️ 模型保存失败")
                else:
                    current = get_config("model", "deepseek-v4-flash")
                    out.append(f"当前模型: {current}")
                    for m in list_available_models():
                        out.append(f"  {m['id']} — {m['name']}: {m['description']}")
            except Exception:
                out.append("模型切换失败")
        elif cmd == "/export":
            try:
                from .utils import export_conversation
                data = self.ai_history or [{"role": r, "content": c} for r, c in self.messages]
                fmt = "json" if cmd_arg.lower() == "json" else "markdown"
                path = export_conversation(data, format=fmt)
                out.append(f"已导出: {path}" if path else "没有可导出的内容")
            except Exception:
                out.append("导出失败")
        elif cmd == "/todo":
            try:
                from .tools.todo_tools import todo_add, todo_list, todo_done, todo_delete
                sub_parts = cmd_arg.split(maxsplit=1)
                sub = sub_parts[0].lower() if sub_parts else "list"
                sub_arg = sub_parts[1] if len(sub_parts) > 1 else ""
                if sub == "list":
                    out.append(todo_list())
                elif sub == "add" and sub_arg:
                    out.append(todo_add(sub_arg))
                elif sub == "done" and sub_arg:
                    try:
                        out.append(todo_done(int(sub_arg)))
                    except ValueError:
                        out.append("待办 ID 必须是数字")
                elif sub in ("del", "delete") and sub_arg:
                    try:
                        out.append(todo_delete(int(sub_arg)))
                    except ValueError:
                        out.append("待办 ID 必须是数字")
                else:
                    out.append("用法: /todo [list|add 任务|done 编号|del 编号]")
            except Exception:
                out.append("待办操作失败")
        elif cmd == "/update":
            try:
                from .utils import check_for_updates
                out.append(check_for_updates())
            except Exception:
                out.append("无法检查更新")
        else:
            out.append(f"未知命令: {cmd}，输入 /help 查看帮助")

        with self._lock:
            lines = list(out)
        for line in lines:
            self._add_message("system", line)

    # ═══════════════ prompt_toolkit 全屏应用 ═══════════════

    def _build_style(self) -> None:
        """根据当前主题构建 prompt_toolkit Style（/theme 切换后重新调用）"""
        from prompt_toolkit.styles import Style
        from .utils import get_theme

        theme = get_theme()

        def c(name: str, default: str = "#d0d0d0") -> str:
            return _RICH_TO_PT_COLOR.get(name, default)

        self.style = Style.from_dict({
            "chat.user": f"fg:{c(theme.get('user_color'))}",
            "chat.ai": f"fg:{c(theme.get('ai_color'))} bold",
            "chat.sys": f"fg:{c(theme.get('system_color'))}",
            "chat.tool": f"fg:{c(theme.get('accent'))}",
        })
        if self.app is not None:
            self.app.style = self.style

    def _build_pt(self, output=None) -> None:
        """构建 prompt_toolkit 全屏应用

        Args:
            output: 可注入的输出后端（测试用；默认自动探测终端）
        """
        kb = KeyBindings()

        @kb.add("c-c")
        def _exit(event):
            event.app.exit()

        @kb.add("pageup")
        def _pageup(event):
            # 向上回看 10 行（上限按实际行数，避免 10**6 卡死）
            with self._lock:
                n = _render_line_count()
            self._back_lines = min(self._back_lines + 10, max(0, n - 1))
            self._invalidate()

        @kb.add("pagedown")
        def _pagedown(event):
            with self._lock:
                n = _render_line_count()
            self._back_lines = max(0, min(self._back_lines, n - 1) - 10)
            self._invalidate()

        @kb.add("c-home")
        def _to_top(event):
            self._back_lines = 10 ** 6
            self._invalidate()

        @kb.add("c-end")
        def _to_bottom(event):
            self._back_lines = 0
            self._invalidate()

        self.input_buffer = Buffer(
            multiline=False,
            history=InMemoryHistory(),
            accept_handler=lambda buff: self._on_accept(buff),
        )

        self.message_window = Window(
            content=FormattedTextControl(
                self._render_messages,
                get_cursor_position=self._get_cursor_position,  # 直接锚定滚动位置
            ),
            wrap_lines=True,
            always_hide_cursor=True,
        )
        # 输入行：左侧模式指示 + 右侧输入框（固定底部）
        mode_window = Window(
            content=FormattedTextControl(self._left_prompt),
            width=Dim(max=12),
            height=1,
            always_hide_cursor=True,
        )
        input_window = Window(
            content=BufferControl(buffer=self.input_buffer, focusable=True),
            height=Dim(min=1, max=3),
        )
        input_row = VSplit([mode_window, input_window])

        self.layout = Layout(
            HSplit([self.message_window, input_row]),
            focused_element=input_window,
        )
        self._build_style()
        self.app = Application(
            layout=self.layout,
            key_bindings=kb,
            style=self.style,
            full_screen=True,
            mouse_support=True,
            output=output,
        )

    def _on_accept(self, buff: Buffer) -> None:
        """输入框提交：优先响应待回答的交互（原子取走，防竞态）"""
        text = buff.text
        with self._lock:
            pending = self._pending_ask
        if pending is not None:
            stripped = text.strip()
            if stripped.startswith("/"):
                # 确认期间输入命令：回退给命令处理，不消费确认（用户可先 /history 等）
                with self._lock:
                    self._pending_ask = pending  # 保留确认状态
                self._handle_input(text)
            else:
                with self._lock:
                    self._pending_ask = None
                pending["callback"](text)
        else:
            self._handle_input(text)
        buff.reset()

    # ═══════════════ 入口 ═══════════════

    def run(self) -> int:
        """运行聊天界面（阻塞直到退出）"""
        if not self._setup_client():
            if self.ai_only:
                print("❌ AI 客户端不可用（请先执行 lank set 配置 API Key）")
                return 1

        if not self._pt_ok:
            return self._run_fallback()

        # 惰性清理过期记忆（best-effort，30 天前的会话与摘要）
        try:
            from .memory import cleanup_old_memories
            cleanup_old_memories()
        except Exception:
            pass

        self._build_pt()

        # 全屏期间静默终端日志输出（stderr 告警会打花备用屏幕）
        from .logs import set_console_logging
        set_console_logging(False)
        try:
            # 初始问题（lank ai "..." 启动即执行）
            if self.initial_question:
                self._handle_input(self.initial_question)

            try:
                self.app.run()
            except KeyboardInterrupt:
                # 双重 Ctrl+C 硬中断也正常退出，不抛 traceback
                pass
        finally:
            set_console_logging(True)

        # 退出前：若 AI 线程仍在跑，先给它一点时间完成保存（防对话丢失）
        if self._ai_running:
            with self._lock:
                self._streamed_parts = []
            deadline = time.time() + 3
            while self._ai_running and time.time() < deadline:
                time.sleep(0.05)

        # 退出：会话总结 + 画像抽取（记忆系统）
        # 放后台线程执行（短超时），绝不阻塞退出；最多等 5 秒
        if self.ai_history and self.session_id and self.session_id not in self._finalized_sessions:
            def _finalize():
                try:
                    from .memory import finalize_session, extract_and_update_profile
                    finalize_session(self.session_id, self.ai_history)
                    if get_config("memory_auto_extract", True):
                        extract_and_update_profile(self.ai_history)
                except BaseException:
                    pass  # 总结失败不影响退出

            t = threading.Thread(target=_finalize, daemon=True)
            t.start()
            t.join(5)

        # 会话统计
        try:
            from .utils import record_session
            msg_count = len([m for r, _ in self.messages if r in ("user", "assistant")])
            record_session(msg_count, self.tool_count)
        except Exception:
            pass
        return 0

    def _run_fallback(self) -> int:
        """prompt_toolkit 不可用时的降级模式"""
        print("⚠️ 未安装 prompt_toolkit，使用降级模式（建议: pip install prompt_toolkit）")
        if self.initial_question:
            print(f"你: {self.initial_question}")
        while True:
            try:
                text = input("[{}] ".format("AI" if self.ai_mode else "普通")).strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not text:
                continue
            if text.lower() in ("exit", "quit"):
                break
            if text.startswith("/"):
                self._handle_command(text)
                continue
            print(f"你: {text}")
            if self.ai_mode and self.ai_available and self.client is not None:
                t = threading.Thread(target=self._run_ai, args=(text,), daemon=True)
                t.start()
                while t.is_alive():
                    time.sleep(0.1)
            else:
                print(f"AI: {FIXED_REPLY}")
        # 降级模式也尝试会话总结（非阻塞）
        if self.ai_history and self.session_id:
            try:
                from .memory import finalize_session, extract_and_update_profile
                t = threading.Thread(
                    target=lambda: (finalize_session(self.session_id, self.ai_history),
                                    extract_and_update_profile(self.ai_history)
                                    if get_config("memory_auto_extract", True) else None),
                    daemon=True)
                t.start()
                t.join(5)
            except BaseException:
                pass
        return 0


def run_tui() -> int:
    """运行 TUI 聊天界面（全屏，输入框固定底部）"""
    return ChatApp(ai_only=False).run()


def run_ai_chat(initial_question: Optional[str] = None, client=None) -> int:
    """运行 AI 全屏聊天界面（lank ai，输入框固定底部）"""
    return ChatApp(ai_only=True, initial_question=initial_question, client=client).run()
