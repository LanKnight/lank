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
| `model` | 模型名称 | `deepseek-v4-flash` |
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

## 🏗️ 系统架构

### 分层架构图

```
┌─────────────────────────────────────────────────┐
│                   CLI 入口层                      │
│  lank tui  │  lank ai  │  lank set  │  lank ... │
│           __main__.py  →  cli.py                │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────┐
│                   核心业务层                       │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ AIClient │  │  Memory  │  │    Config      │  │
│  │ (API调用)│  │  (记忆)  │  │ (~/.lank/)     │  │
│  └────┬─────┘  └──────────┘  └───────┬───────┘  │
│       │                              │          │
│  ┌────┴──────────────────────────────┴───────┐  │
│  │         model_config (模型参数)            │  │
│  └───────────────────────────────────────────┘  │
│  ┌──────────┐  ┌──────────────────────────────┐  │
│  │   TUI    │  │           utils              │  │
│  │ (聊天UI) │  │ (主题/统计/导出/更新检查)     │  │
│  └──────────┘  └──────────────────────────────┘  │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────┐
│                  工具系统 (Tools)                 │
│  ┌──────────────────────────────────────────┐   │
│  │         tools/__init__.py                 │   │
│  │   注册表 _tool_registry: Dict[str,Tool]   │   │
│  │   register / execute / get_all / needs_   │   │
│  └──────────────────────────────────────────┘   │
│  ┌──────────┐ ┌──────────┐ ┌──────┐ ┌───────┐  │
│  │file_ops  │ │cmd_exec  │ │system│ │ todo  │  │
│  │ 6 tools  │ │ 1 tool   │ │  3   │ │   4   │  │
│  └──────────┘ └──────────┘ └──────┘ └───────┘  │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────┐
│               外部依赖 & 持久化                    │
│  DeepSeek API  │  ~/.lank/config.json           │
│  OpenAI SDK    │  ~/.lank/memory/               │
│  Rich / prompt_toolkit  │  ~/.lank/todos.json   │
└─────────────────────────────────────────────────┘
```

### 一次 AI 对话的完整路径

以 `lank ai "帮我读 README"` 为例，追踪请求从 CLI 到 API 再回到用户的全过程：

```
用户输入 "lank ai 帮我读README"
  │
  ├─ __main__.py:main()
  │    └─ cli.py:cli(["ai", "帮我读README"])
  │
  ├─ cli.py:run_ai_chat("帮我读README")
  │    ├─ load_config()           ← 检查 api_key 是否配置
  │    ├─ AIClient.__init__()     ← 加载配置、验证、初始化 OpenAI 客户端
  │    │    ├─ get_config()       ← 读取 api_key / api_base / model
  │    │    ├─ _looks_like_api_key()  ← 防止 api_key 填到 api_base
  │    │    └─ OpenAI(api_key, base_url, timeout, max_retries)
  │    │
  │    └─ client.chat(messages, stream=True, on_tool_call, on_text)
  │         │
  │         ├─ _build_system_prompt()
  │         │    ├─ get_config("system_prompt")     ← 读用户自定义提示词
  │         │    ├─ get_tool_descriptions()         ← 生成工具说明文本
  │         │    └─ build_system_prompt()           ← 组装最终 system prompt
  │         │
  │         ├─ _create_completion(messages, stream=True)
  │         │    └─ OpenAI.chat.completions.create(
  │         │         model, messages,
  │         │         tools=get_all_tools(),   ← 14 个注册工具→OpenAI schema
  │         │         temperature, max_tokens, stream=True
  │         │       )
  │         │
  │         ├─ _accumulate_stream(stream, on_text)
  │         │    ├─ for chunk in stream:
  │         │    │    ├─ delta.content → on_text(delta)  ← 实时打字效果
  │         │    │    └─ delta.tool_calls → 按 index 拼接片段
  │         │    └─ return (完整文本, tool_calls列表)
  │         │
  │         ├─ [如果 AI 要调用工具]
  │         │    ├─ for each tool_call:
  │         │    │    ├─ needs_approval(name) → on_tool_call() ← 用户确认
  │         │    │    └─ execute_tool(name, args)
  │         │    │         └─ tools/__init__.py → tool func(**args)
  │         │    │
  │         │    └─ _run_tool_loop()      ← 非流式多轮循环
  │         │         ├─ assistant(tool_calls) msg ← 必须先于 tool results!
  │         │         ├─ tool results msg
  │         │         ├─ _create_completion(stream=False)
  │         │         └─ 重复直到无工具调用 or 达到 MAX_TOOL_CALL_ROUNDS
  │         │
  │         └─ return (success, final_response, updated_messages)
  │
  └─ save_conversation(history)   ← memory 模块持久化到 ~/.lank/memory/
```

### 模块依赖关系

```
__main__ ──→ cli ──→ config ──→ model_config
            │  │
            │  ├──→ tui ──→ config, memory
            │  │
            │  ├──(lazy)──→ ai_client ──→ config, model_config, tools
            │  │
            │  └──→ memory ──→ config
            │
            └──(lazy)──→ utils ──→ config

tools/__init__ ──→ tools/file_ops ──→ tools/__init__ (register_tool)
               ├─→ tools/cmd_exec ──→ tools/__init__
               ├─→ tools/system ────→ tools/__init__
               └─→ tools/todo_tools → tools/__init__
```

> **注意:** `ai_client` 和 `utils` 使用懒加载（try/except ImportError），确保在未安装 `openai` 时 `lank tui` 仍可正常运行。工具模块与 `tools/__init__.py` 之间存在有意的循环导入——子模块导入 `register_tool`，而 `__init__.py` 在底部导入子模块以触发工具注册。

---

## 📖 代码阅读路线

如果你是第一次阅读这个项目的源码，以下是推荐的阅读顺序。

### 推荐阅读顺序

| 顺序 | 文件 | 关注点 | 预计 |
|:----:|------|--------|:----:|
| 1 | `lank/__init__.py` → `__main__.py` | 项目入口，了解启动方式 | 1 min |
| 2 | `lank/cli.py` | CLI 命令路由 + AI 聊天主循环，理解命令分发和对话流程 | 10 min |
| 3 | `lank/model_config.py` | 模型定义、参数、提示词组装，纯配置+工具函数，无外部依赖 | 3 min |
| 4 | `lank/config.py` | 配置持久化、环境变量覆盖、交互式配置向导 | 5 min |
| 5 | `lank/tools/__init__.py` | **工具注册表模式**，理解 `register → get_all → execute` 三步走 | 5 min |
| 6 | `lank/tools/file_ops.py` 等 4 个工具模块 | 实际工具实现——学完这个就知道如何添加新工具 | 各 3-5 min |
| 7 | `lank/ai_client.py` | **核心模块**：流式解析 + 工具调用循环，项目最复杂的文件 | 15 min |
| 8 | `lank/memory.py` | 对话历史持久化 + 用户画像，独立模块，可单独阅读 | 5 min |
| 9 | `lank/tui.py` | prompt_toolkit 实现的 TUI 界面，与 `cli.py` 是平行的 UI 入口 | 可选 |
| 10 | `lank/utils.py` | 主题 / 统计 / 导出 / 更新检查，独立工具集，无复杂逻辑 | 可选 |

### 三条阅读路径

- 🟢 **快速路径**（理解骨架）：`1 → 2 → 3 → 5`，了解入口 → 路由 → 模型配置 → 工具注册即可把握全局
- 🟡 **标准路径**（理解全貌）：按顺序 `1 → 8` 全部阅读，覆盖所有核心模块
- 🔴 **扩展路径**（想添加功能）：
  - 添加新工具 → 重点读 `5 → 6`（工具注册 + 一个工具模块当模板）
  - 添加新模型 → 重点读 `3 → 4`（模型配置 + 配置管理）
  - 修改对话逻辑 → 重点读 `7`（AIClient）

### 关键设计模式

整个项目围绕几个核心模式构建，理解它们是读懂代码的关键：

**1. 工具注册表** (`tools/__init__.py`)

添加新工具只需两步：写一个函数 + 调一行 `register_tool()`。AI 客户端完全不感知具体工具——它只通过 `get_all_tools()` 获取 OpenAI 格式的 schema，通过 `execute_tool()` 调度执行。

```python
# 添加新工具: tools/my_tool.py
from . import register_tool

def my_func(arg1: str) -> str:
    return f"处理结果: {arg1}"

register_tool(
    name="my_tool",
    description="我的自定义工具",
    func=my_func,
    parameters=[{"name": "arg1", "type": "string", "description": "参数1"}],
    requires_approval=False,  # True = 需要用户确认
)
```

**2. 配置优先级** (`config.py`)

```
环境变量 (OPENAI_API_KEY 等)  >  配置文件 (~/.lank/config.json)  >  默认值
```

`load_config()` 逐层合并，后覆盖前。`AIClient.__init__` 还有自动修复逻辑——如果用户把 API Key 填到了 `api_base` 字段，会自动检测并修正。

**3. 流式 + 工具循环混合** (`ai_client.py`)

这是一个巧妙的双模式设计：
- **首轮请求** 使用流式输出，`_accumulate_stream()` 实时回调每个 token 给 UI 渲染，同时从 chunk 中拼装 tool_calls。
- **工具调用循环** 切换到非流式，`_run_tool_loop()` 严格控制消息顺序：必须 `assistant(tool_calls)` → `tool(result)` → ...，循环最多 `MAX_TOOL_CALL_ROUNDS` 轮。

**4. 模型回退机制** (`model_config.py`)

`get_model(name)` 在 `MODELS` 字典中查找，找不到则返回 `FALLBACK_MODEL`。这意味着老的配置项（如之前的 `deepseek-chat`）不会报错，而是自动回退到 `deepseek-v4-flash`。

### 数据存储布局

所有持久化数据都在 `~/.lank/` 下，纯 JSON 文件，无需数据库：

```
~/.lank/
├── config.json          # 用户配置（API Key、模型、主题等）
├── stats.json           # 使用统计
├── todos.json           # 待办事项
├── memory/
│   ├── history/         # 对话历史 (YYYYMMDD_HHMMSS.json)
│   └── profile.json     # 用户画像
└── exports/             # 对话导出 (Markdown / JSON)
```

---

## 📄 许可证

本项目采用 MIT 许可证。

---

**享受你的私人 AI 终端助手吧！** 😄
