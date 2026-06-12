"""
配置管理模块 - 管理 ~/.lank/config.json
支持 lank set 交互式配置
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

CONFIG_DIR = Path.home() / ".lank"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "completed": False,
    "api_key": "",
    "api_base": "https://api.deepseek.com",
    "model": "deepseek-chat",
    "user_name": "用户",
    "ai_name": "LANK",
    "temperature": 0.7,
    "max_tokens": 4096,
    "system_prompt": "你是一个智能终端助手，可以帮助用户完成各种任务，包括文件操作、命令执行、代码分析等。请用中文回复。",
    "theme": "default",
    "working_dir": str(Path.cwd()),
    "safe_mode": True,  # 危险操作前是否需要确认
    "memory_enabled": True,
    "max_history": 100,
}


def ensure_config_dir() -> None:
    """确保配置目录存在"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> Dict[str, Any]:
    """加载配置，如果文件不存在则返回默认配置"""
    ensure_config_dir()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # 合并默认配置，确保新字段存在
            merged = DEFAULT_CONFIG.copy()
            merged.update(cfg)
            return merged
        except (json.JSONDecodeError, IOError):
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()


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


def print_config(config: Dict[str, Any]) -> None:
    """以可读格式打印配置"""
    print("\n" + "=" * 50)
    print("  📋 LANK 当前配置")
    print("=" * 50)
    
    # 敏感信息脱敏
    display_config = config.copy()
    if display_config.get("api_key"):
        key = display_config["api_key"]
        if len(key) > 8:
            display_config["api_key"] = key[:4] + "*" * (len(key) - 8) + key[-4:]
        else:
            display_config["api_key"] = "****"
    
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
    
    # 显示帮助
    print("用法:")
    print("  lank set              - 交互式配置向导")
    print("  lank set show         - 查看当前配置")
    print("  lank set reset        - 重置配置")
    print("  lank set get <key>    - 获取配置项")
    print("  lank set set <k> <v>  - 设置配置项")
    return 0
