@echo off
chcp 65001 >nul

:: ============================================================
:: LANK - 私人 AI 终端助手 启动脚本
:: 支持在任何目录下运行
:: ============================================================

:: 检查 Python
py --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [31m❌ 未找到 Python，请先安装 Python 3.8+[0m
    pause
    exit /b 1
)

:: 直接使用 py -m lank 运行
py -m lank %*
exit /b %errorlevel%
