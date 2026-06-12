# lank - 私人 AI 终端助手

一个轻量级的私人 AI 终端助手，基于用户日常使用习惯构建专属个性化记忆，支持终端交互与日常琐事任务执行。

> 🚀 **模型选择**: DeepSeek

---

## ✨ 主要特性

### 🎯 三大核心命令

| 命令 | 功能 |
|------|------|
| `lank tui` | 启动 TUI 聊天界面（支持 `/ai` 切换 AI 模式） |
| `lank ai` | 启动 AI 聊天界面（支持工具调用，可带初始问题） |
| `lank set` | 交互式配置向导 |

### 🤖 AI 智能助手（`lank ai`）
- 调用 DeepSeek API 进行智能对话
- **工具调用能力**（类似 Claude）：
  - 📁 **文件操作**：读取、写入、搜索、替换文件内容
  - 💻 **命令执行**：运行终端命令并获取输出
  - 🔍 **代码分析**：查看项目结构、搜索代码定义
  - 📅 **系统信息**：日期时间、系统信息查询、数学计算
  - 📝 **待办管理**：添加、查看、完成、删除待办事项
- 带 Rich 渲染的聊天界面，支持思考动画、工具调用确认

### 🧠 个性化记忆
- 自动保存对话历史
- 跨会话记忆恢复
- 用户偏好学习（用户画像）

### 🎨 美观的 TUI 界面（`lank tui`）
- 彩色面板和时间戳
- 命令历史和智能提示
- 思考动画和流式输出
- ASCII AI 头像

### 🎪 创意功能
- **🎨 主题系统**：5 种主题（默认/暗色/赛博朋克/黑客/日落）
- **📊 使用统计**：记录会话数、消息数、工具调用次数
- **💾 对话导出**：支持 Markdown 和 JSON 格式导出
- **🔄 版本检查**：自动检查 GitHub 最新版本

---

## 🛠️ 技术栈

- **Python 3.8+**
- **rich >= 12.0** - 终端美化和格式化输出
- **prompt_toolkit >= 3.0** - 交互式命令行输入
- **openai >= 1.0.0**（可选）- AI API 调用

---

## 📦 安装方法

### 方式一：直接运行（推荐用于测试）

```powershell
cd d:\aboutWork\lank
pip install -r requirements.txt
python -m lank tui
```

### 方式二：Windows 快捷方式

```powershell
.\lank.cmd tui
```

### 方式三：安装为全局命令（推荐长期使用）

```powershell
pip install --user .
# 或安装全部功能（含 AI）
pip install --user ".[all]"
```

---

## 🎮 使用方法

### 启动 TUI 聊天界面

```powershell
lank tui
```

在 TUI 中：
- 输入 `/ai` 切换到 AI 智能模式（需先配置 API Key）
- 输入 `/normal` 切换回普通聊天模式
- 输入 `/help` 查看帮助
- 输入 `/clear` 清空对话
- 输入 `/save` 保存对话
- 输入 `exit` 退出

### 启动 AI 聊天界面

```powershell
# 直接启动 AI 聊天界面（交互式）
lank ai

# 带初始问题启动
lank ai 你好
lank ai 帮我读一下当前目录的文件
lank ai 帮我计算 123 * 456
```

在 AI 聊天界面中：
- 输入 `/clear` 清空对话历史
- 输入 `/help` 查看帮助
- 输入 `/save` 保存对话
- 输入 `/stats` 查看使用统计
- 输入 `/theme` 查看当前主题
- 输入 `exit` 退出

### 配置管理

```powershell
# 交互式配置向导
lank set

# 查看当前配置
lank set show

# 设置 API Key
lank set set api_key sk-your-key-here

# 获取配置项
lank set get model

# 重置配置
lank set reset
```

---

## 🔧 配置项

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `api_key` | DeepSeek API 密钥 | - |
| `api_base` | API 地址 | `https://api.deepseek.com` |
| `model` | 模型名称 | `deepseek-chat` |
| `user_name` | 用户称呼 | `用户` |
| `ai_name` | AI 名称 | `LANK` |
| `temperature` | 温度参数 (0-2) | `0.7` |
| `max_tokens` | 最大 Token 数 | `4096` |
| `system_prompt` | 系统提示词 | 内置默认提示词 |
| `theme` | 界面主题 | `default` |
| `safe_mode` | 安全模式（危险操作前确认） | `true` |
| `working_dir` | 工作目录 | 当前目录 |
| `memory_enabled` | 记忆功能 | `true` |
| `max_history` | 最大历史记录数 | `100` |

---

## 📝 示例

### 文件操作
```powershell
> lank ai 帮我创建一个 hello.py 文件，打印 "Hello LANK"
🔧 AI 调用工具: write_to_file
✅ 已写入文件: hello.py

> lank ai 读取 hello.py 的内容
📄 文件内容:
1 | print("Hello LANK")
```

### 命令执行
```powershell
> lank ai 查看当前目录有哪些文件
🔧 AI 调用工具: list_files
📁 src/
📄 README.md
📄 hello.py
```

### 待办管理
```powershell
> lank ai 帮我添加一个待办：完成项目文档
✅ 已添加待办 [#1]: 完成项目文档

> lank ai 显示我的待办列表
📋 待办事项列表
⬜ [#1] 🟡 完成项目文档
```

---

## 🗂️ 项目结构

```
lank/
├── lank/
│   ├── __init__.py          # 包初始化（版本号）
│   ├── __main__.py          # 主入口
│   ├── cli.py               # CLI 命令处理 + AI 聊天界面
│   ├── config.py            # 配置管理（lank set）
│   ├── tui.py               # TUI 聊天界面
│   ├── ai_client.py         # AI 客户端（DeepSeek API + 工具调用）
│   ├── memory.py            # 个性化记忆模块
│   ├── utils.py             # 工具函数（主题/统计/导出/更新检查）
│   └── tools/               # 工具模块
│       ├── __init__.py      # 工具注册与调度
│       ├── file_ops.py      # 文件操作（6 个工具）
│       ├── cmd_exec.py      # 命令执行（1 个工具）
│       ├── system.py        # 系统工具（3 个工具）
│       └── todo_tools.py    # 待办管理（4 个工具）
├── README.md
├── pyproject.toml
├── requirements.txt
├── lank.cmd
└── todo.md
```

---

## 📄 许可证

本项目采用 MIT 许可证。

---

**享受你的私人 AI 终端助手吧！** 😄
