"""
模型配置模块 — 管理 AI 模型相关的所有配置参数
支持 DeepSeek 和 OpenAI 兼容 API 的模型配置

将所有模型相关参数集中在此文件，便于：
  - 切换模型 / 提供商
  - 调整提示词策略
  - 管理不同模型的参数差异
"""

from typing import Any, Dict, List, Optional

# ============================================================
# API 连接参数
# ============================================================

DEFAULT_API_BASE = "https://api.deepseek.com"

# OpenAI 兼容客户端参数
CLIENT_TIMEOUT = 30.0         # 请求超时（秒）
CLIENT_MAX_RETRIES = 2        # 失败重试次数

# ============================================================
# 模型列表 — 全部为 DeepSeek 模型
# ============================================================

# 每个模型的独立默认值；缺省字段回退到全局 DEFAULT_MODEL_PARAMS
MODELS: Dict[str, Dict[str, Any]] = {
    "deepseek-chat": {
        "name": "DeepSeek Chat",
        "description": "通用对话模型，适合日常助手任务",
        "max_tokens": 4096,
        "supports_tools": True,
    },
    "deepseek-reasoner": {
        "name": "DeepSeek Reasoner",
        "description": "推理增强模型，适合复杂分析任务",
        "max_tokens": 4096,
        "supports_tools": True,
    },
    "deepseek-coder": {
        "name": "DeepSeek Coder",
        "description": "代码专项模型，适合编程相关任务",
        "max_tokens": 4096,
        "supports_tools": True,
    },
}

# 当前使用的模型名称
DEFAULT_MODEL = "deepseek-chat"

# 当用户未在配置中指定模型名，或指定的模型不在 MODELS 中时，回退至此值
FALLBACK_MODEL = "deepseek-chat"

# ============================================================
# 模型参数默认值
# ============================================================

DEFAULT_MODEL_PARAMS: Dict[str, Any] = {
    "temperature": 0.7,       # 0-2，越高越有创造性
    "max_tokens": 4096,       # 单次回复最大 token 数
    "top_p": 1.0,             # 核采样参数
    "frequency_penalty": 0.0, # 重复惩罚
    "presence_penalty": 0.0,  # 主题多样性
}

# 工具调用循环安全限制
MAX_TOOL_CALL_ROUNDS = 10    # 单次对话中最多连续工具调用轮数，防止无限循环

# ============================================================
# 系统提示词
# ============================================================

DEFAULT_SYSTEM_PROMPT = (
    "你是一个智能终端助手，可以帮助用户完成各种任务，"
    "包括文件操作、命令执行、代码分析等。请用中文回复。"
)

# 工具调用规则提示词（追加到系统提示词后）
TOOL_USAGE_PROMPT = """
## 工具调用规则
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

# ============================================================
# 便捷函数
# ============================================================

def get_model(name: Optional[str] = None) -> Dict[str, Any]:
    """获取指定模型的配置，若不存在则返回默认模型"""
    model_name = name or DEFAULT_MODEL
    if model_name in MODELS:
        return MODELS[model_name]
    # 回退到默认模型
    return MODELS.get(FALLBACK_MODEL, {})


def get_model_param(model_name: Optional[str], param: str, default: Any = None) -> Any:
    """获取某个模型参数的当前值

    优先级：模型专属值 > DEFAULT_MODEL_PARAMS > default 参数
    """
    if model_name and model_name in MODELS:
        model_cfg = MODELS[model_name]
        if param in model_cfg:
            return model_cfg[param]

    if param in DEFAULT_MODEL_PARAMS:
        return DEFAULT_MODEL_PARAMS[param]

    return default


def list_available_models() -> List[Dict[str, Any]]:
    """列出所有可用模型及其摘要"""
    result = []
    for key, cfg in MODELS.items():
        result.append({
            "id": key,
            "name": cfg.get("name", key),
            "description": cfg.get("description", ""),
            "max_tokens": cfg.get("max_tokens", DEFAULT_MODEL_PARAMS["max_tokens"]),
            "supports_tools": cfg.get("supports_tools", True),
        })
    return result


def build_system_prompt(base_prompt: str = "", tool_desc: str = "") -> str:
    """组装最终的系统提示词（base + 工具描述 + 工具规则 + 回复风格）"""
    prompt = base_prompt or DEFAULT_SYSTEM_PROMPT

    if tool_desc:
        prompt += f"\n\n你拥有以下工具可以使用，当用户需要时，请调用相应的工具来完成任务：\n{tool_desc}"

    prompt += TOOL_USAGE_PROMPT
    return prompt
