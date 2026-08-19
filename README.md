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

### 🤖 AI 智能助手（`lank ai`，v0.3.0 起接入 ReAct 框架）
- 调用 DeepSeek API 进行智能对话
- **🧭 ReAct 三阶段框架**（`lank/agent/`）：
  - **分类**：简单问答直接回答；复杂业务自动进入规划
  - **PLAN 规划**：任务自动拆解为带验收标准的步骤计划，执行前展示给你确认（`/auto` 可全自动）
  - **ACT 执行**：按计划逐步执行，每步独立上下文 + 步骤验收（防上下文爆炸）
  - **REVIEW 审核**：对照验收标准逐条审核，未达标自动补充步骤重跑
- **工具调用能力**（23 个工具）：
  - 📁 **文件操作**：读取、写入、搜索、替换文件内容
  - 💻 **命令执行**：运行终端命令并获取输出（安全升级：危险命令黑名单 + 输出截断 + 白名单）
  - 🔍 **代码分析**：查看项目结构、搜索代码定义
  - 📅 **系统信息**：日期时间、系统信息查询、数学计算
  - 📝 **待办管理**：添加、查看、完成、删除待办事项
  - 🧭 **规划工具**：提交计划、登记步骤完成、向用户提问
  - 🧠 **记忆工具**：`memory_search` / `memory_recall` / `memory_remember` / `memory_forget`
- 带 Rich 渲染的聊天界面，支持流式输出、工具调用确认（可永久放行白名单）

### 🧠 个性化记忆系统（`lank/memory/`）
- 自动保存对话历史 + 跨会话记忆恢复
- **四层记忆架构**：工作记忆（任务内）/ 情景记忆（会话摘要）/ 语义记忆（事实与偏好）/ 程序性记忆（规划中）
- **会话滚动摘要**：会话结束自动总结；长会话按 token 阈值增量压缩
- **自动画像抽取**：从对话中自动学习你的偏好与事实（`memory_auto_extract`），也可显式 `memory_remember`
- **关键词加权检索**：按 相关性×新鲜度×重要性 注入相关记忆（「提前的加载」）

### 🎨 全屏聊天界面（`lank tui` / `lank ai`）
- **输入框固定在屏幕最底部**，消息内容向上滚动堆积（不再清屏闪烁）
- **历史可回看**：`PageUp` / `PageDown` 向上/向下翻看历史消息
- 消息区实时渲染：用户消息、AI 流式输出、工具调用、计划与审核状态
- 普通 / AI 双模式（`/ai` 切换），AI 模式走 ReAct 框架（AgentLoop 后台线程执行）
- 工具确认 / 提问在输入框内完成（y=允许 / n=拒绝 / a=总是允许加入白名单）
- 5 套主题配色、命令历史和智能提示

### 🎪 更多功能
- **🎨 主题系统**：5 种主题（默认/暗色/赛博朋克/黑客/日落），`/theme <name>` 实时切换
- **📊 使用统计**：`/stats` 查看会话数、消息数、工具调用次数
- **💾 对话导出**：`/export` 导出为 Markdown 或 JSON
- **🔄 版本检查**：`/update` 检查 GitHub 最新版本
- **📝 待办管理**：`/todo` 在聊天中直接管理待办
- **🔀 模型切换**：`/model` 查看和切换 AI 模型

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

在 TUI 中（全屏聊天界面，输入框固定底部）：
- 输入 `/ai` 切换到 AI 智能模式（需先配置 API Key）
- 输入 `/normal` 切换回普通聊天模式
- 按 `PageUp` / `PageDown` 回看历史消息
- 输入 `/help` 查看所有命令
- 输入 `/clear` 清空对话
- 输入 `/save` 保存对话
- 输入 `/export [json]` 导出对话
- 输入 `/stats` 查看使用统计
- 输入 `/theme [名称]` 显示或切换主题
- 输入 `/model [名称]` 显示或切换 AI 模型
- 输入 `/todo list|add|done|del` 管理待办
- 输入 `/auto` 切换自动模式（计划自动确认、审核自动通过）
- 输入 `/update` 检查更新
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

在 AI 聊天界面中（同样为全屏界面，输入框固定底部）：
- 输入 `/clear` 清空对话历史
- 按 `PageUp` / `PageDown` 回看历史消息
- 输入 `/auto` 切换自动模式（计划自动确认、审核自动通过）
- 输入 `/help` 查看所有命令
- 输入 `/save` 保存对话
- 输入 `/stats` 查看使用统计
- 输入 `/theme [名称]` 显示或切换主题
- 输入 `/model [名称]` 显示或切换 AI 模型
- 输入 `/export [json]` 导出对话
- 输入 `/todo list|add|done|del` 管理待办
- 输入 `/update` 检查更新
- 输入 `exit` 退出

> 💡 **复杂任务流程**：输入一个复杂需求（如"帮我搭一个 Python 项目脚手架"），
> AI 会先展示执行计划（步骤 + 验收标准），确认后逐步执行，最后自动审核交付；
> 审核不达标会自动补充步骤重跑。`/auto` 开启后全程无需确认。
> **执行全程实时显示进度**：`⏳ 步骤 X/Y` → `❓ 工具确认` → `🔧 正在执行工具` → 工具结果 → `✅ 步骤完成`，
> 长线任务不会"黑屏无反馈"。

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
| `max_history` | 最大历史记录数（会话滑动窗口） | `100` |
| `auto_mode` | 自动模式（计划自动确认、审核自动通过） | `false` |
| `max_plan_steps` | 单计划最大步骤数 | `10` |
| `max_review_rounds` | 审核未达标最大迭代轮数 | `3` |
| `plan_prompt` / `exec_prompt` / `review_prompt` | 覆盖各阶段系统提示词 | - |
| `tool_output_limit` | 工具结果截断字符数 | `8192` |
| `cmd_output_limit` | 命令输出截断字符数 | `20480` |
| `cmd_timeout` | 命令执行超时（秒） | `60` |
| `cmd_allowlist` | 命令白名单（可自动执行） | `[]` |
| `api_max_retries` | API 429/5xx 退避重试次数 | `2` |
| `memory_summary_max_chars` | 会话摘要长度上限 | `2000` |
| `memory_long_session_threshold` | 长会话增量总结 token 阈值 | `20000` |
| `memory_top_k` | 记忆检索注入条数 | `5` |
| `memory_max_facts` | 语义记忆容量上限 | `200` |
| `memory_auto_extract` | 会话后自动抽取画像 | `true` |

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
│   ├── cli.py               # CLI 命令处理 + AI 聊天界面（ReAct 接入）
│   ├── config.py            # 配置管理（lank set，带缓存）
│   ├── tui.py               # TUI 聊天界面
│   ├── ai_client.py         # AI 客户端（DeepSeek API + 工具循环 + 重试）
│   ├── logs.py              # 日志系统（~/.lank/logs/）
│   ├── utils.py             # 工具函数（主题/统计/导出/原子写）
│   ├── agent/               # ★ ReAct 框架层
│   │   ├── types.py         # 数据模型（Plan/Step/ReviewVerdict）
│   │   ├── prompts.py       # PLAN/EXEC/REVIEW 三段提示词
│   │   ├── planner.py       # 分类 + 规划
│   │   ├── executor.py      # 按步骤执行（每步紧凑上下文）
│   │   ├── reviewer.py      # 验收审核
│   │   ├── loop.py          # AgentLoop 状态机
│   │   └── context.py       # 工具与循环的通信上下文
│   ├── memory/              # ★ 记忆子系统（原 memory.py 升级）
│   │   ├── __init__.py      # 对外 API（兼容旧调用）
│   │   ├── store.py         # 持久化（会话/摘要/事实/画像）
│   │   ├── summarizer.py    # 会话总结器（结束总结 + 长会话增量）
│   │   ├── extractor.py     # 画像抽取器
│   │   ├── retriever.py     # 关键词加权检索器
│   │   └── forget.py        # 遗忘清理
│   └── tools/               # 工具模块（23 个工具）
│       ├── __init__.py      # 工具注册/调度/校验/截断/白名单
│       ├── file_ops.py      # 文件操作（6 个工具）
│       ├── cmd_exec.py      # 命令执行（安全版：黑名单/截断）
│       ├── system.py        # 系统工具（3 个工具）
│       ├── todo_tools.py    # 待办管理（4 个工具）
│       ├── plan_tools.py    # ★ 规划工具（submit_plan/step_done/ask_user 等）
│       └── memory_tools.py  # ★ 记忆工具（memory_search/remember 等）
├── docs/
│   └── design.md            # ★ ReAct 框架 + 记忆系统设计文档
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
│                 Agent 框架层 (agent/)             │
│   ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│   │ Planner  │  │ Executor │  │  Reviewer    │  │
│   │(分类+规划)│  │(逐步执行) │  │ (验收审核)   │  │
│   └────┬─────┘  └────┬─────┘  └──────┬───────┘  │
│        └─────────────┴───────────────┘          │
│              AgentLoop (状态机)                  │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────┐
│                   核心业务层                       │
│  ┌──────────┐  ┌──────────────┐  ┌───────────┐  │
│  │ AIClient │  │ Memory (包)  │  │  Config   │  │
│  │(API+重试) │  │ 四层记忆     │  │(~/.lank/) │  │
│  └────┬─────┘  └──────┬───────┘  └─────┬─────┘  │
│  ┌────┴────────────────┴───────────────┴─────┐  │
│  │         model_config (模型参数)            │  │
│  └───────────────────────────────────────────┘  │
│  ┌──────────┐  ┌──────────────────────────────┐  │
│  │   TUI    │  │           utils              │  │
│  │ (聊天UI) │  │ (主题/统计/导出/原子写)       │  │
│  └──────────┘  └──────────────────────────────┘  │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────┐
│                  工具系统 (Tools)                 │
│  ┌──────────────────────────────────────────┐   │
│  │        tools/__init__.py (v2)            │   │
│  │   注册表 + 校验 + 截断 + 白名单            │   │
│  │   category / danger_level / approval     │   │
│  └──────────────────────────────────────────┘   │
│  ┌───────┐┌───────┐┌──────┐┌──────┐┌────────┐  │
│  │file_ops│cmd_exec│system│ todo │plan_tools│  │
│  │  6    │ 1(安全) │  3   │  4   │   5     │  │
│  └───────┘└───────┘└──────┘└──────┘└────────┘  │
│  ┌──────────────┐                               │
│  │ memory_tools │ 4 个记忆工具                   │
│  └──────────────┘                               │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────┐
│               外部依赖 & 持久化                    │
│  DeepSeek API  │  ~/.lank/config.json           │
│  OpenAI SDK    │  ~/.lank/memory/               │
│  Rich / prompt_toolkit  │  ~/.lank/todos.json   │
│  ~/.lank/logs/ │  ~/.lank/allowlist.json        │
└─────────────────────────────────────────────────┘
```

### 一次 AI 对话的完整路径（ReAct）

以 `lank ai "帮我搭建一个 Python 项目脚手架"` 为例：

```
用户输入（复杂业务）
  │
  ├─ cli.py:run_ai_chat → AgentLoop.run(input, memory_text)
  │    ├─ get_relevant_context(input)   ← 「提前的加载」：检索相关记忆
  │    │
  │    ├─ [1] Planner.plan_or_answer()  ← 一次流式请求
  │    │     ├─ PLAN_PROMPT + 记忆 + 工具描述
  │    │     ├─ 简单问答 → 直接流式回答（不进框架）
  │    │     └─ 复杂任务 → 模型调用 submit_plan → Plan（步骤+验收标准）
  │    │
  │    ├─ [2] 计划确认（on_plan_render + on_plan_confirm）
  │    │     └─ 用户确认 / /auto 自动通过
  │    │
  │    ├─ [3] Executor.execute_plan()   ← 每步独立紧凑上下文
  │    │     ├─ EXEC_PROMPT（目标+当前步+前步摘要）
  │    │     ├─ 工具循环（确认/白名单）→ 步骤完成调 step_done
  │    │     └─ 步骤结果摘要 → 下一步
  │    │
  │    └─ [4] Reviewer.review()  ← 可迭代
  │          ├─ REVIEW_PROMPT（对照验收标准逐条核对）
  │          ├─ 可交付 → 总结交付（用户终审）
  │          └─ 未达标 → 追加 new_steps → 回到 [3]（最多 N 轮）
  │
  └─ 退出：finalize_session（会话摘要）+ extract_and_update_profile（画像抽取）
```

### 模块依赖关系

```
__main__ ──→ cli ──→ config ──→ model_config
            │  │
            │  ├──→ tui ──→ config, memory
            │  │
            │  ├──(lazy)──→ agent ──→ planner/executor/reviewer/loop
            │  │              │
            │  │              └──→ ai_client ──→ config, model_config, tools
            │  │
            │  ├──→ memory ──→ config, utils(原子写)
            │  │
            │  └──(lazy)──→ utils ──→ config

tools/__init__ ──→ file_ops / cmd_exec / system / todo_tools
               ├─→ plan_tools ──→ agent.context（与运行中的 AgentLoop 通信）
               └─→ memory_tools ──→ memory（检索/写入）
```

> **注意:** `ai_client` 和 `utils` 使用懒加载（try/except ImportError），确保在未安装 `openai` 时 `lank tui` 仍可正常运行。工具模块与 `tools/__init__.py` 之间存在有意的循环导入——子模块导入 `register_tool`，而 `__init__.py` 在底部导入子模块以触发工具注册。`plan_tools`/`memory_tools` 通过 `agent.context` 与运行中的 `AgentLoop` 通信，避免直接循环依赖。

---

## 📖 代码阅读路线

如果你是第一次阅读这个项目的源码，以下是推荐的阅读顺序。

### 推荐阅读顺序

| 顺序 | 文件 | 关注点 | 预计 |
|:----:|------|--------|:----:|
| 1 | `lank/__init__.py` → `__main__.py` | 项目入口，了解启动方式 | 1 min |
| 2 | `lank/cli.py` | CLI 命令路由 + AI 聊天主循环（ReAct 接入点） | 10 min |
| 3 | `lank/model_config.py` | 模型定义、参数、提示词组装，纯配置+工具函数，无外部依赖 | 3 min |
| 4 | `lank/config.py` | 配置持久化（带缓存）、环境变量覆盖、交互式配置向导 | 5 min |
| 5 | `lank/tools/__init__.py` | **工具注册表模式**，`register → get_all → execute`，v2 元数据/校验/白名单 | 5 min |
| 6 | `lank/agent/types.py` → `loop.py` | **ReAct 框架核心**：数据模型 + 状态机（plan→act→review） | 10 min |
| 7 | `lank/agent/planner.py` → `executor.py` → `reviewer.py` | 三个阶段实现，理解紧凑上下文与验收标准 | 10 min |
| 8 | `lank/memory/` | 四层记忆：store/summarizer/extractor/retriever/forget | 10 min |
| 9 | `lank/ai_client.py` | 底层 API：流式解析 + 工具循环 + 退避重试 | 10 min |
| 10 | `lank/tui.py` / `utils.py` | UI 入口与工具集 | 可选 |

### 三条阅读路径

- 🟢 **快速路径**（理解骨架）：`1 → 2 → 3 → 5`，了解入口 → 路由 → 模型配置 → 工具注册即可把握全局
- 🟡 **标准路径**（理解全貌）：按顺序 `1 → 8` 全部阅读，覆盖所有核心模块
- 🔴 **扩展路径**（想添加功能）：
  - 添加新工具 → 重点读 `5 → 6`（工具注册 + 一个工具模块当模板）
  - 修改 Agent 流程 → 重点读 `6 → 7`（AgentLoop + 三个阶段）
  - 添加新模型 → 重点读 `3 → 4`（模型配置 + 配置管理）
  - 修改记忆逻辑 → 重点读 `8`（memory/ 包）

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

**5. ReAct 状态机** (`agent/loop.py`)

`AgentLoop` 是核心状态机：分类 → PLAN（拆解任务）→ ACT（每步紧凑上下文执行）→ REVIEW（对照验收标准）→ 未达标自动迭代。三个阶段通过 `planner`/`executor`/`reviewer` 实现，UI 层只提供回调（`AgentCallbacks`），框架与界面完全解耦。

**6. 工具-循环通信** (`agent/context.py`)

规划/执行/审核工具（`submit_plan`/`step_done`/`submit_review`）是模块级注册函数，通过 `agent.context` 的当前循环引用与运行中的 `AgentLoop` 通信，避免工具注册表与框架的循环依赖。

### 数据存储布局

所有持久化数据都在 `~/.lank/` 下，纯 JSON 文件，无需数据库（全部原子写入）：

```
~/.lank/
├── config.json          # 用户配置（API Key、模型、主题、ReAct/记忆参数等）
├── stats.json           # 使用统计
├── todos.json           # 待办事项
├── allowlist.json       # 工具/命令白名单（确认时可永久放行）
├── logs/                # 日志（lank.log，滚动保留 3 份）
├── memory/
│   ├── history/         # 原始会话 (YYYYMMDD_HHMMSS_xxxx.json)
│   ├── summaries.json   # 情景记忆：会话摘要（LLM 生成）
│   ├── facts.json       # 语义记忆：事实/偏好（来源/重要性/提及次数）
│   └── profile.json     # 用户画像（由 facts 聚合，兼容旧格式）
└── exports/             # 对话导出 (Markdown / JSON)
```

---

## 📄 许可证

本项目采用 MIT 许可证。

---

**享受你的私人 AI 终端助手吧！** 😄
