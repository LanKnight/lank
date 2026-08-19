"""
日志模块 - 统一日志记录
日志写入 ~/.lank/logs/lank.log，同时输出到 stderr
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path.home() / ".lank" / "logs"
LOG_FILE = LOG_DIR / "lank.log"

_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    """初始化日志系统（幂等）"""
    global _configured
    if _configured:
        return

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=1_048_576, backupCount=3, encoding="utf-8"
        )
    except Exception:
        file_handler = None

    handlers = []
    if file_handler is not None:
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        handlers.append(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)  # 终端只显示警告及以上
    console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    handlers.append(console_handler)

    root = logging.getLogger("lank")
    root.setLevel(level)
    if not root.handlers:
        for h in handlers:
            root.addHandler(h)
    _configured = True


def get_logger(name: str = "lank") -> logging.Logger:
    """获取 lank 命名空间下的 logger"""
    setup_logging()
    return logging.getLogger(f"lank.{name}" if name != "lank" else "lank")
