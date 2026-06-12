"""
lank - 私人 AI 终端助手
主入口模块
"""

import sys

from .cli import cli


def main():
    """主入口函数"""
    raise SystemExit(cli())


if __name__ == "__main__":
    main()
