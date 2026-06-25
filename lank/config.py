"""
配置管理模块 - 管理 ~/.lank/config.json
支持 lank set 交互式配置
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .model_config import (
    DEFAULT_API_BASE,
    DEFAULT_MODEL,
    DEFAULT_MODEL_PARAMS,
    DEFAULT_SYSTEM_PROMPT,
)

CONFIG_DIR = Path.home() / ".lank"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "completed": False,
    "api_key": "",
    "api_base": DEFAULT_API_BASE,
    "model": DEFAULT_MODEL,
    "user_name": "用户",
    "ai_name": "LANK",
    "temperature": DEFAULT_MODEL_PARAMS["temperature"],
    "max_tokens": DEFAULT_MODEL_PARAMS["max_tokens"],
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
    "theme": "default",
    "working_dir": "",  # 空字符串表示使用当前工作目录（os.getcwd()）
    "safe_mode": True,  # 危险操作前是否需要确认
    "memory_enabled": True,
    "max_history": 100,
}



def ensure_config_dir() -> None:
    """确保配置目录存在"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> Dict[str, Any]:
    """加载配置，如果文件不存在则返回默认配置
    
    优先级（从高到低）：
    1. 环境变量 OPENAI_API_KEY（如果设置了，会覆盖配置文件中的值）
    2. 配置文件 ~/.lank/config.json
    3. 默认配置
    """
    ensure_config_dir()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # 合并默认配置，确保新字段存在
            merged = DEFAULT_CONFIG.copy()
            merged.update(cfg)
        except (json.JSONDecodeError, IOError):
            merged = DEFAULT_CONFIG.copy()
    else:
        merged = DEFAULT_CONFIG.copy()
    
    # 环境变量覆盖：OPENAI_API_KEY
    env_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if env_key:
        merged["api_key"] = env_key
    
    # 环境变量覆盖：OPENAI_API_BASE
    env_base = os.environ.get("OPENAI_API_BASE", "").strip()
    if env_base:
        merged["api_base"] = env_base
    
    # 环境变量覆盖：OPENAI_MODEL
    env_model = os.environ.get("OPENAI_MODEL", "").strip()
    if env_model:
        merged["model"] = env_model
    
    return merged



def save_config(config: Dict[str, Any]) -> bool:
    """保存配置到文件"""
    ensure_config_dir()
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except IOError as e:
        print(f"保存配置失败: {e}")
        return False


def get_config(key: str, default: Any = None) -> Any:
    """获取单个配置项"""
    config = load_config()
    return config.get(key, default)


def set_config(key: str, value: Any) -> bool:
    """设置单个配置项"""
    config = load_config()
    config[key] = value
    return save_config(config)


def get_working_dir() -> str:
    """获取当前工作目录
    
    优先使用 os.getcwd()（命令执行时的当前目录），
    如果配置中设置了 working_dir 且不为空，则使用配置值。
    """
    config = load_config()
    configured_dir = config.get("working_dir", "")
    if configured_dir and os.path.isdir(configured_dir):
        return configured_dir
    return os.getcwd()



def _mask_sensitive_value(value: str) -> str:
    """脱敏敏感值（API Key 等）"""
    if not value:
        return "⚠️ 未设置"
    if value.startswith("sk-") or value.startswith("org-"):
        if len(value) > 12:
            return value[:6] + "*" * (len(value) - 10) + value[-4:]
        return "****"
    return value


def _looks_like_api_key(value: str) -> bool:
    """判断值是否看起来像 API Key 而非 URL"""
    if not value:
        return False
    return (value.startswith("sk-") or value.startswith("org-")) and not value.startswith("http")


def validate_config(config: Dict[str, Any]) -> List[str]:
    """验证配置，返回警告列表"""
    warnings = []

    # 检查 api_key 未设置
    if not config.get("api_key"):
        warnings.append("⚠️ 未设置 api_key，AI 功能不可用。请执行: lank set")

    # 检查 api_base 是否像 API Key（填反了）
    api_base = config.get("api_base", "")
    if _looks_like_api_key(api_base):
        warnings.append(
            f"⚠️ api_base 的值看起来像 API Key（以 sk- 开头），"
            f"你可能把 api_key 填到了 api_base 字段。"
            f"\n  💡 请执行: lank set set api_base {DEFAULT_API_BASE}"
        )

    # 检查 api_base 是否包含 /v1 后缀（OpenAI SDK 会自动加）
    if api_base.endswith("/v1") or api_base.endswith("/v1/"):
        warnings.append(
            "⚠️ api_base 地址末尾的 /v1 是多余的（SDK 会自动追加）。"
        )

    # 检查 temperature 范围
    temp = config.get("temperature", 0.7)
    if isinstance(temp, (int, float)) and not 0 <= temp <= 2:
        warnings.append(f"⚠️ temperature 应在 0-2 范围内，当前为 {temp}")

    return warnings


def print_config(config: Dict[str, Any]) -> None:
    """以可读格式打印配置"""
    print("\n" + "=" * 50)
    print("  📋 LANK 当前配置")
    print("=" * 50)

    # 敏感信息脱敏
    display_config = config.copy()
    if display_config.get("api_key"):
        display_config["api_key"] = _mask_sensitive_value(display_config["api_key"])
    if display_config.get("api_base"):
        display_config["api_base"] = _mask_sensitive_value(display_config["api_base"])

    for key, value in display_config.items():
        if key == "completed":
            continue
        # 格式化输出
        key_str = key.replace("_", " ").title()
        if isinstance(value, bool):
            value_str = "✅ 是" if value else "❌ 否"
        elif isinstance(value, str) and not value:
            value_str = "⚠️ 未设置"
        else:
            value_str = str(value)
        
        # 标记来自环境变量的配置项
        if key == "api_key" and os.environ.get("OPENAI_API_KEY", "").strip():
            value_str += " [环境变量]"
        elif key == "api_base" and os.environ.get("OPENAI_API_BASE", "").strip():
            value_str += " [环境变量]"
        elif key == "model" and os.environ.get("OPENAI_MODEL", "").strip():
            value_str += " [环境变量]"
        
        print(f"  {key_str:20s}: {value_str}")
    print("=" * 50 + "\n")



def run_setup_wizard() -> None:
    """运行交互式配置向导"""
    config = load_config()
    
    print("\n" + "=" * 50)
    print("  🔧 LANK 配置向导")
    print("=" * 50)
    print("  (直接回车保持当前值不变)")
    print()
    
    # API Key
    current = config.get("api_key", "")
    hint = current[:4] + "****" if current else "未设置"
    val = input(f"  DeepSeek API Key [{hint}]: ").strip()
    if val:
        config["api_key"] = val
    
    # API Base
    current = config.get("api_base", DEFAULT_CONFIG["api_base"])
    val = input(f"  API 地址 [{current}]: ").strip()
    if val:
        if _looks_like_api_key(val):
            print("  ⚠️ 这看起来像 API Key 而不是 URL！")
            print(f"     请输入 API 地址（如 {DEFAULT_API_BASE}），API Key 请填在上一步。")
            print("     本次输入已忽略，保持原值。")
        else:
            config["api_base"] = val
    
    # Model
    current = config.get("model", DEFAULT_CONFIG["model"])
    val = input(f"  模型名称 [{current}]: ").strip()
    if val:
        config["model"] = val
    
    # User name
    current = config.get("user_name", DEFAULT_CONFIG["user_name"])
    val = input(f"  你的称呼 [{current}]: ").strip()
    if val:
        config["user_name"] = val
    
    # AI name
    current = config.get("ai_name", DEFAULT_CONFIG["ai_name"])
    val = input(f"  AI 名称 [{current}]: ").strip()
    if val:
        config["ai_name"] = val
    
    # Temperature
    current = config.get("temperature", DEFAULT_CONFIG["temperature"])
    val = input(f"  温度参数 (0-2, 默认 {current}): ").strip()
    if val:
        try:
            config["temperature"] = float(val)
        except ValueError:
            print("  ⚠️ 无效值，使用默认值")
    
    # Safe mode
    current = config.get("safe_mode", DEFAULT_CONFIG["safe_mode"])
    val = input(f"  安全模式 (危险操作前确认) [{'y' if current else 'n'}]: ").strip().lower()
    if val in ("y", "yes", "true"):
        config["safe_mode"] = True
    elif val in ("n", "no", "false"):
        config["safe_mode"] = False
    
    # Working directory
    current = config.get("working_dir", str(Path.cwd()))
    val = input(f"  工作目录 [{current}]: ").strip()
    if val:
        if os.path.isdir(val):
            config["working_dir"] = val
        else:
            print(f"  ⚠️ 目录不存在: {val}，使用当前值")
    
    config["completed"] = True

    if save_config(config):
        print("\n  ✅ 配置保存成功！")
        print_config(config)

        # 配置验证
        warnings = validate_config(config)
        if warnings:
            print("  ── 配置检查 ──")
            for w in warnings:
                print(f"  {w}")
            print()
    else:
        print("\n  ❌ 配置保存失败！")


def run_set_command(args: list) -> int:
    """处理 lank set 命令"""
    if not args:
        # 无参数，运行交互式向导
        run_setup_wizard()
        return 0
    
    subcmd = args[0]
    
    if subcmd == "show":
        config = load_config()
        print_config(config)
        warnings = validate_config(config)
        if warnings:
            print("  ⚠️ 配置检查：")
            for w in warnings:
                print(f"  {w}")
            print()
        return 0
    
    if subcmd == "reset":
        print("  确定要重置所有配置吗？[y/N]")
        ans = input().strip().lower()
        if ans == "y":
            if save_config(DEFAULT_CONFIG.copy()):
                print("  ✅ 配置已重置")
            else:
                print("  ❌ 重置失败")
        return 0
    
    if subcmd == "set" and len(args) >= 3:
        key = args[1]
        value = args[2]
        # 尝试转换类型
        if value.lower() in ("true", "false"):
            value = value.lower() == "true"
        elif value.isdigit():
            value = int(value)
        else:
            try:
                value = float(value)
            except ValueError:
                pass
        if set_config(key, value):
            print(f"  ✅ 已设置 {key} = {value}")
        else:
            print(f"  ❌ 设置失败")
        return 0
    
    if subcmd == "get" and len(args) >= 2:
        value = get_config(args[1])
        print(f"  {args[1]} = {value}")
        return 0

    if subcmd == "verify":
        config = load_config()
        warnings = validate_config(config)
        if warnings:
            print("\n  ⚠️ 发现以下配置问题：\n")
            for w in warnings:
                print(f"  {w}")
            print()
        else:
            print("\n  ✅ 配置检查通过，未发现问题。\n")
        return 0

    # 显示帮助
    print("用法:")
    print("  lank set              - 交互式配置向导")
    print("  lank set show         - 查看当前配置")
    print("  lank set reset        - 重置配置")
    print("  lank set verify       - 验证配置是否正确")
    print("  lank set get <key>    - 获取配置项")
    print("  lank set set <k> <v>  - 设置配置项")
    return 0
