"""
AI 客户端模块 - 调用 DeepSeek API
支持工具调用（function calling）能力 + 流式输出
"""

import json
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

from .config import get_config, set_config, _looks_like_api_key
from .model_config import (
    DEFAULT_API_BASE,
    DEFAULT_MODEL,
    CLIENT_TIMEOUT,
    CLIENT_MAX_RETRIES,
    MAX_TOOL_CALL_ROUNDS,
    get_model_param,
    build_system_prompt,
)
from .tools import get_all_tools, get_tool_descriptions, execute_tool, needs_approval


# 尝试导入 openai 库
try:
    from openai import OpenAI
    from openai import APIConnectionError, APIError, AuthenticationError, RateLimitError
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


def _build_tool_call_dict(tc: Any) -> Dict[str, Any]:
    """将 OpenAI tool_call 对象转换为 API 消息格式"""
    return {
        "id": tc.id,
        "type": "function",
        "function": {
            "name": tc.function.name,
            "arguments": tc.function.arguments,
        },
    }


def _safe_display_url(url: str) -> str:
    """安全显示 URL/地址，防止 API Key 在错误信息中泄漏"""
    if not url:
        return "(未设置)"
    if url.startswith("sk-") or url.startswith("org-"):
        if len(url) > 12:
            return url[:6] + "****" + url[-4:]
        return "****"
    return url


# ── 流式响应工具函数 ──

def _accumulate_stream(
    stream_response: Any,
    on_text: Optional[Callable] = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """消费 OpenAI 流式响应，实时回调 on_text，返回 (完整内容, 工具调用列表)

    Args:
        stream_response: OpenAI SDK 返回的流式迭代器
        on_text: 每次收到文本增量时调用 on_text(delta_str)

    Returns:
        (完整文本, tool_calls 列表，格式为 API 消息 dict)
    """
    content_parts: List[str] = []
    # 按 index 累积 tool call 片段
    tc_buf: Dict[int, Dict[str, Any]] = {}

    for chunk in stream_response:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta is None:
            continue

        # ── 文本增量 ──
        if delta.content:
            content_parts.append(delta.content)
            if on_text:
                on_text(delta.content)

        # ── 工具调用增量（分多个 chunk 到达） ──
        if delta.tool_calls:
            for tc_delta in delta.tool_calls:
                idx = tc_delta.index
                if idx not in tc_buf:
                    tc_buf[idx] = {"id": "", "function_name": "", "arguments": ""}

                entry = tc_buf[idx]
                if tc_delta.id:
                    entry["id"] = tc_delta.id
                if tc_delta.function:
                    if tc_delta.function.name:
                        entry["function_name"] = tc_delta.function.name
                    if tc_delta.function.arguments:
                        entry["arguments"] += tc_delta.function.arguments

    # 组装 tool_calls
    tool_calls: List[Dict[str, Any]] = []
    for idx in sorted(tc_buf.keys()):
        tc = tc_buf[idx]
        if tc["function_name"]:
            tool_calls.append({
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["function_name"],
                    "arguments": tc["arguments"],
                },
            })

    return "".join(content_parts), tool_calls


# ── AIClient ──

class AIClient:
    """AI 客户端，封装 DeepSeek API 调用和工具调用逻辑"""

    def __init__(self, auto_fix: bool = True):
        self.api_key = get_config("api_key", "")
        self.api_base = get_config("api_base", DEFAULT_API_BASE)
        self.model = get_config("model", DEFAULT_MODEL)

        # ── 配置验证 ──
        self._config_warnings: List[str] = []

        if _looks_like_api_key(self.api_base):
            self._config_warnings.append(
                "⚠️ api_base 的值看起来像是 API Key（以 sk- 开头），"
                "你可能把 api_key 填到了 api_base 字段。"
            )
            if auto_fix:
                if not self.api_key:
                    set_config("api_key", self.api_base)
                    set_config("api_base", DEFAULT_API_BASE)
                    self.api_key = self.api_base
                    self.api_base = DEFAULT_API_BASE
                    self._config_warnings[-1] += "\n  ✅ 已自动修复：将 api_base 的值移到了 api_key。"
                else:
                    self._config_warnings[-1] += (
                        f"\n  💡 请执行: lank set set api_base {DEFAULT_API_BASE}"
                    )

        self.temperature = get_model_param(
            self.model, "temperature",
            get_config("temperature", 0.7),
        )
        self.max_tokens = get_model_param(
            self.model, "max_tokens",
            get_config("max_tokens", 4096),
        )
        self.ai_name = get_config("ai_name", "LANK")
        self.user_name = get_config("user_name", "用户")
        self.safe_mode = get_config("safe_mode", True)

        self.client = None
        self._init_client()

    def _init_client(self) -> None:
        """初始化 OpenAI 客户端"""
        if not HAS_OPENAI:
            return
        if not self.api_key:
            return
        try:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.api_base,
                timeout=CLIENT_TIMEOUT,
                max_retries=CLIENT_MAX_RETRIES,
            )
        except Exception as e:
            print(f"初始化 AI 客户端失败: {e}")

    def is_ready(self) -> Tuple[bool, str]:
        """检查客户端是否就绪"""
        if not HAS_OPENAI:
            return False, "缺少 openai 库，请执行: pip install openai"
        if not self.api_key:
            return False, "未配置 API Key，请执行: lank set"
        if not self.client:
            return False, "AI 客户端初始化失败"
        suffix = ""
        if self._config_warnings:
            suffix = "\n" + "\n".join(self._config_warnings)
        return True, "就绪" + suffix

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        base_prompt = get_config("system_prompt", "")
        tool_desc = get_tool_descriptions()
        return build_system_prompt(base_prompt, tool_desc)

    def _format_error(self, error: Exception) -> str:
        """格式化错误信息（不暴露敏感信息）"""
        error_str = str(error)
        safe_base = _safe_display_url(self.api_base)

        if "Connection error" in error_str or "connection" in error_str.lower():
            lines = [
                "❌ 网络连接失败，请检查：",
                "  1. 网络是否正常连接",
                f"  2. API 地址是否正确 (当前: {safe_base})",
                "  3. 是否需要配置代理 (设置 HTTP_PROXY/HTTPS_PROXY 环境变量)",
            ]
            if self._config_warnings:
                lines.append("")
                lines.extend(self._config_warnings)
            return "\n".join(lines)
        if "Authentication" in error_str or "auth" in error_str.lower() or "401" in error_str:
            return "❌ API Key 认证失败，请检查 API Key 是否正确 (lank set set api_key 你的key)"
        if "Rate limit" in error_str or "429" in error_str:
            return "❌ 请求过于频繁，请稍后再试"
        if "timeout" in error_str.lower():
            return "❌ 请求超时，请检查网络连接或稍后再试"
        if "model" in error_str.lower() and "not found" in error_str.lower():
            return f"❌ 模型 '{self.model}' 不存在，请检查模型名称 (lank set set model 模型名)"

        return f"❌ AI 请求失败: {error_str}"

    # ── 底层 API 调用 ──

    def _create_completion(self, messages: List[Dict[str, Any]], *, stream: bool):
        """统一的 API 调用入口"""
        tools = get_all_tools()
        return self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools if tools else None,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=stream,
        )

    def _run_tool_loop(
        self,
        messages: List[Dict[str, Any]],
        system_msg: Dict[str, Any],
        on_tool_call: Optional[Callable],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """非流式工具调用循环

        在首轮 tool_calls 已追加到 messages 之后调用。
        顺序严格保证：assistant(tool_calls) → tool(result) → ... → assistant(final)

        Returns:
            (final_text_content, updated_messages)
        """
        # 发送当前 messages（含首轮 tool_calls + tool results）获取下一轮响应
        response = self._create_completion([system_msg] + messages, stream=False)
        choice = response.choices[0]
        assistant_msg = choice.message

        tool_round = 1
        while assistant_msg.tool_calls and tool_round < MAX_TOOL_CALL_ROUNDS:
            tool_round += 1

            # ⭐ 必须先把 assistant（含 tool_calls）追加到 messages，
            #    然后再追加 tool results，否则 API 报错：
            #    "tool must be a response to a preceding tool_calls"
            msg_dict: Dict[str, Any] = {
                "role": "assistant",
                "content": assistant_msg.content or "",
            }
            if assistant_msg.tool_calls:
                msg_dict["tool_calls"] = [
                    _build_tool_call_dict(tc) for tc in assistant_msg.tool_calls
                ]
            messages.append(msg_dict)

            # 执行本轮所有工具
            for tool_call in assistant_msg.tool_calls:
                func_name = tool_call.function.name
                try:
                    func_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    func_args = {}

                if needs_approval(func_name) and self.safe_mode:
                    if on_tool_call:
                        proceed = on_tool_call(func_name, func_args)
                        if not proceed:
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": "操作已取消",
                            })
                            continue

                _, result = execute_tool(func_name, func_args)

                if on_tool_call:
                    on_tool_call(func_name, func_args, result)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

            # 继续获取下一轮
            response = self._create_completion([system_msg] + messages, stream=False)
            choice = response.choices[0]
            assistant_msg = choice.message

        # ── 达到上限但仍需工具调用 → 追加警告，不追加未执行的 tool_calls ──
        if tool_round >= MAX_TOOL_CALL_ROUNDS and assistant_msg.tool_calls:
            warning = (
                f"⚠️ 已达到最大工具调用轮次 ({MAX_TOOL_CALL_ROUNDS})，"
                "请简化你的请求或分步执行。"
            )
            messages.append({"role": "assistant", "content": warning})
            return warning, messages

        # ── 正常结束：无工具调用，追加最终回复 ──
        messages.append({
            "role": "assistant",
            "content": assistant_msg.content or "",
        })
        return assistant_msg.content or "", messages

    # ── 公开接口 ──

    def chat(
        self,
        messages: List[Dict[str, Any]],
        stream: bool = True,
        on_tool_call: Optional[Callable] = None,
        on_text: Optional[Callable] = None,
    ) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """与 AI 对话

        Args:
            messages: 对话历史（不含 system message）
            stream:   True → 流式输送到 on_text；False → 一次性返回
            on_tool_call: 工具调用回调 (name, args, result=None) -> bool
            on_text:      文本回调 (delta: str)，流式模式下每个 token 调用一次

        Returns:
            (success, final_response, updated_messages)
        """
        ready, msg = self.is_ready()
        if not ready:
            return False, msg, messages

        system_msg = {"role": "system", "content": self._build_system_prompt()}

        try:
            # ── 首次请求：流式 ──
            if stream:
                stream_resp = self._create_completion(
                    [system_msg] + messages, stream=True,
                )
                content, tool_calls = _accumulate_stream(stream_resp, on_text=on_text)
            else:
                response = self._create_completion(
                    [system_msg] + messages, stream=False,
                )
                choice = response.choices[0]
                assistant_msg = choice.message
                content = assistant_msg.content or ""
                tool_calls = []
                if assistant_msg.tool_calls:
                    tool_calls = [_build_tool_call_dict(tc) for tc in assistant_msg.tool_calls]
                if on_text and content:
                    on_text(content)

            # ── 记录 assistant 消息 ──
            assistant_entry: Dict[str, Any] = {"role": "assistant", "content": content}
            if tool_calls:
                assistant_entry["tool_calls"] = tool_calls
            messages.append(assistant_entry)

            # ── 如果没有工具调用，直接返回 ──
            if not tool_calls:
                return True, content, messages

            # ── 首轮工具执行（将 tool_calls 转为可执行形式） ──
            for tc_dict in tool_calls:
                func_name = tc_dict["function"]["name"]
                try:
                    func_args = json.loads(tc_dict["function"]["arguments"])
                except json.JSONDecodeError:
                    func_args = {}

                if needs_approval(func_name) and self.safe_mode:
                    if on_tool_call:
                        proceed = on_tool_call(func_name, func_args)
                        if not proceed:
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc_dict["id"],
                                "content": "操作已取消",
                            })
                            continue

                _, result = execute_tool(func_name, func_args)

                if on_tool_call:
                    on_tool_call(func_name, func_args, result)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_dict["id"],
                    "content": result,
                })

            # ── 工具循环（非流式处理中间轮次） ──
            final_content, messages = self._run_tool_loop(
                messages, system_msg, on_tool_call,
            )

            return True, final_content, messages

        except AuthenticationError:
            return False, "❌ API Key 认证失败，请检查 API Key 是否正确 (lank set set api_key 你的key)", messages
        except RateLimitError:
            return False, "❌ 请求过于频繁，请稍后再试", messages
        except APIConnectionError:
            safe_base = _safe_display_url(self.api_base)
            lines = [
                "❌ 网络连接失败，请检查：",
                "  1. 网络是否正常连接",
                f"  2. API 地址是否正确 (当前: {safe_base})",
                "  3. 是否需要配置代理 (设置 HTTP_PROXY/HTTPS_PROXY 环境变量)",
            ]
            if self._config_warnings:
                lines.append("")
                lines.extend(self._config_warnings)
            return False, "\n".join(lines), messages
        except APIError as e:
            return False, f"❌ API 错误: {e}", messages
        except Exception as e:
            return False, self._format_error(e), messages


def simple_chat(user_input: str, history: Optional[List[Dict]] = None) -> None:
    """简单的对话入口（用于命令行直接对话）"""
    if history is None:
        history = []

    client = AIClient()
    ready, msg = client.is_ready()
    if not ready:
        print(f"❌ {msg}")
        return

    history.append({"role": "user", "content": user_input})

    def on_tool_call(name, args, result=None):
        if result is None:
            print(f"\n🔧 AI 想要调用工具: [bold]{name}[/bold]")
            print(f"   参数: {json.dumps(args, ensure_ascii=False)}")
            ans = input("   是否允许? [Y/n]: ").strip().lower()
            return ans not in ("n", "no")
        else:
            print(f"\n🔧 工具 [{name}] 执行结果:")
            print(f"   {result[:200]}{'...' if len(result) > 200 else ''}")
            return True

    def on_text(text):
        if text:
            print(text, end="", flush=True)

    print("\n🤖 ", end="", flush=True)
    success, response, history = client.chat(
        messages=history,
        stream=True,
        on_tool_call=on_tool_call,
        on_text=on_text,
    )
    print()  # 换行

    if not success:
        print(f"❌ {response}")
