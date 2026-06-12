"""
AI 客户端模块 - 调用 DeepSeek API
支持工具调用（function calling）能力
"""

import json
import sys
from typing import Any, Dict, List, Optional, Tuple

from .config import get_config
from .tools import get_all_tools, get_tool_descriptions, execute_tool, needs_approval


# 尝试导入 openai 库
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


class AIClient:
    """AI 客户端，封装 DeepSeek API 调用和工具调用逻辑"""
    
    def __init__(self):
        self.api_key = get_config("api_key", "")
        self.api_base = get_config("api_base", "https://api.deepseek.com")
        self.model = get_config("model", "deepseek-chat")
        self.temperature = get_config("temperature", 0.7)
        self.max_tokens = get_config("max_tokens", 4096)
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
        return True, "就绪"
    
    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        base_prompt = get_config("system_prompt", "")
        tool_desc = get_tool_descriptions()
        
        prompt = base_prompt
        
        if tool_desc:
            prompt += f"\n\n你拥有以下工具可以使用，当用户需要时，请调用相应的工具来完成任务：\n{tool_desc}"
        
        prompt += f"""
\n## 工具调用规则
1. 当用户请求需要操作文件、执行命令或查询系统信息时，优先使用工具
2. 工具调用结果会返回给你，请根据结果继续处理
3. 对于写文件、执行命令等操作，需要先向用户说明你要做什么，等待用户确认
4. 如果工具调用失败，请向用户说明错误原因

## 回复风格
- 用中文回复
- 简洁明了，直接给出结果
- 对于代码相关的问题，提供清晰的代码片段
- 对于文件操作，说明操作内容和结果
"""
        return prompt
    
    def chat(
        self,
        messages: List[Dict[str, Any]],
        stream: bool = True,
        on_tool_call=None,
        on_text=None,
    ) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """与 AI 对话
        
        Args:
            messages: 对话历史
            stream: 是否流式输出
            on_tool_call: 工具调用回调 (tool_name, args) -> bool (是否继续)
            on_text: 文本输出回调 (text)
        
        Returns:
            (success, final_response, updated_messages)
        """
        ready, msg = self.is_ready()
        if not ready:
            return False, msg, messages
        
        # 构建系统提示词
        system_prompt = self._build_system_prompt()
        system_msg = {"role": "system", "content": system_prompt}
        
        # 准备 API 消息
        api_messages = [system_msg] + messages
        
        # 获取工具定义
        tools = get_all_tools()
        
        try:
            # 首次请求
            response = self.client.chat.completions.create(
                model=self.model,
                messages=api_messages,
                tools=tools if tools else None,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=False,
            )
            
            choice = response.choices[0]
            assistant_msg = choice.message
            
            # 更新消息历史
            msg_dict = {"role": "assistant", "content": assistant_msg.content or ""}
            
            # 处理工具调用
            if assistant_msg.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    for tc in assistant_msg.tool_calls
                ]
            
            messages.append(msg_dict)
            
            # 如果有工具调用，循环处理
            while assistant_msg.tool_calls:
                for tool_call in assistant_msg.tool_calls:
                    func_name = tool_call.function.name
                    try:
                        func_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        func_args = {}
                    
                    # 检查是否需要用户确认
                    if needs_approval(func_name) and self.safe_mode:
                        if on_tool_call:
                            proceed = on_tool_call(func_name, func_args)
                            if not proceed:
                                # 用户取消
                                tool_result = "操作已取消"
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": tool_result,
                                })
                                continue
                    
                    # 执行工具
                    success, result = execute_tool(func_name, func_args)
                    
                    if on_tool_call:
                        on_tool_call(func_name, func_args, result)
                    
                    # 添加工具调用结果到消息
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })
                
                # 继续对话，传入工具调用结果
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[system_msg] + messages,
                    tools=tools if tools else None,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    stream=False,
                )
                
                choice = response.choices[0]
                assistant_msg = choice.message
                
                msg_dict = {"role": "assistant", "content": assistant_msg.content or ""}
                
                if assistant_msg.tool_calls:
                    msg_dict["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "arguments": tc.function.arguments,
                        }
                        for tc in assistant_msg.tool_calls
                    ]
                
                messages.append(msg_dict)
            
            final_content = assistant_msg.content or ""
            if on_text:
                on_text(final_content)
            
            return True, final_content, messages
        
        except Exception as e:
            error_msg = f"AI 请求失败: {e}"
            return False, error_msg, messages


def simple_chat(user_input: str, history: Optional[List[Dict]] = None) -> None:
    """简单的对话入口（用于命令行直接对话）"""
    from .config import get_config
    
    if history is None:
        history = []
    
    client = AIClient()
    ready, msg = client.is_ready()
    if not ready:
        print(f"❌ {msg}")
        return
    
    # 添加用户消息
    history.append({"role": "user", "content": user_input})
    
    def on_tool_call(name, args, result=None):
        if result is None:
            # 需要用户确认
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
            print(f"\n🤖 {text}")
    
    success, response, history = client.chat(
        messages=history,
        stream=False,
        on_tool_call=on_tool_call,
        on_text=on_text,
    )
    
    if not success:
        print(f"❌ {response}")
