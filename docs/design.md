# LANK ReAct Agent 框架 — 设计文档

> 状态：**定稿**（2025 讨论确认，待实现）
> 关联：`todo.md` 中「框架结构 ReAct」条目
> 原则：先讨论方案，再写代码。本文档是唯一的设计依据，实现前如需改动，先改本文档。

---

## 1. 背景与目标

LANK 是一个终端 AI 助手，当前 `AIClient.chat()` 是扁平的单轮循环：首轮流式 + 最多 10 轮非流式工具循环。对照 `todo.md` 的要求，缺少三种核心能力：

| todo.md 要求 | 现状 | 差距 |
|---|---|---|
| plan 模式：拆解任务、制定 todo | ❌ 无 | 无计划结构、无任务拆解、无用户可见的计划 |
| act 模式：按计划逐步执行 | ⚠️ 半有 | 只有"连续工具循环"，没有"按步骤推进、每步验收" |
| review 模式：审核可交付性 | ❌ 无 | 执行完直接结束，从不回头检查是否达标 |
| 系统提示词完善 | ⚠️ 单薄 | 只有一个 `TOOL_USAGE_PROMPT`，没有分阶段提示词 |

同时存在四个真实隐患（todo.md 已记录）：

1. **上下文爆炸**：`run_ai_chat` 的 `history` 列表无限增长，每次对话把全部历史 + 全部工具结果原样发给 API，长会话必然爆掉（已见 400 错误：请求 594 万 tokens）。
2. **命令执行危险**：`execute_command` 在 Windows 上用 `shell=True` 拼接执行，无危险命令检测，只有"执行前问一句 Y/n"。
3. **安全模型单一**：`requires_approval` 只有 True/False，没有危险等级、白名单、"本次会话记住"等策略。
4. **记忆存而不用**：`memory.py` 只有存储壳——`get_recent_context()` 注入的是原始截断消息（无总结、无相关性）；`update_profile()` 全项目无调用方（画像永不更新）；`cleanup_old_memories()` 从未接入。

### 设计目标

- 引入 **Plan → Act → Review** 三阶段 ReAct 状态机；
- **验收标准前置**：规划阶段为每个步骤和整体目标定义验收标准，review 阶段逐条对照；
- **上下文可控**：每步独立紧凑上下文 + 会话滑动窗口 + 工具结果截断；
- **安全升级**：命令执行参数化 + 危险命令黑名单 + 输出截断 + 分级确认策略；
- 保持现有 `tools/` 注册表模式，`AIClient` 降级为底层 API 封装，Agent 框架在其上构建，不破坏 `lank tui` 等现有入口。
- **记忆系统升级**：四层记忆（工作/情景/语义/程序）+ 会话滚动摘要 + 自动画像抽取 + 关键词检索，作为框架的持久化底座（详见第 8 节）。

---

## 2. 总体状态机

```
              用户输入
                 │
                 ▼
          ┌─── 分类判定 ───┐
          │（工具调用式合并）│
     简单问答│              │复杂业务
          ▼                ▼
     直接回答          ┌─── PLAN ───┐
    （不进框架）       │ 拆解任务     │
                      │ 生成步骤计划 │
                      │ 用户确认计划 │
                      └─────┬───────┘
                            ▼
                     ┌─── ACT ────┐
                     │ 按步骤执行   │◄─────────┐
                     │ 每步独立上下文│          │
                     │ 每步验收后推进│          │
                     └─────┬───────┘          │
                           ▼                  │
                    ┌─── REVIEW ───┐          │
                    │ 对照验收标准   │          │
                    │ 判定是否可交付 │          │
                    └──┬──────┬────┘          │
                  可交付 │      │ 未达标       │
                       ▼      ▼               │
                   总结交付  补充新步骤为todo   │
                             └────────────────┘
                 （最多迭代 N 轮，防死循环）
```

### 阶段说明

| 阶段 | 职责 | 触发 | 出口 |
|---|---|---|---|
| 分类 | 判定简单问答 / 复杂业务 | 每次用户输入 | 直接回答 或 进入 PLAN |
| PLAN | 任务拆解为步骤计划，每步带验收标准 | 判定为复杂业务 | 用户确认的计划 |
| ACT | 按计划逐步执行，每步独立紧凑上下文 | 计划确认（或 /auto） | 全部步骤 done 或 blocked |
| REVIEW | 对照验收标准判定可交付性 | 全部步骤完成 | 交付总结 或 补充新步骤回到 ACT |

---

## 3. 模块划分

```
lank/
├── agent/                    # ★ 新增 ReAct 框架层
│   ├── __init__.py
│   ├── types.py              # 数据模型：Plan / Step / ReviewVerdict / 枚举
│   ├── planner.py            # PLAN：任务拆解 → submit_plan 工具
│   ├── executor.py           # ACT：每步紧凑上下文 + 工具循环 + 步验收
│   ├── reviewer.py           # REVIEW：对照验收标准 → 结构化判定
│   ├── loop.py               # AgentLoop 状态机（plan→act→review 迭代控制）
│   └── prompts.py            # PLAN/EXEC/REVIEW 三段提示词（可配置覆盖）
├── tools/
│   ├── __init__.py           # 元数据升级：category / danger_level / approval
│   ├── cmd_exec.py           # ★ 重构：参数化执行 + 危险命令黑名单 + 输出截断
│   ├── plan_tools.py         # ★ 新增：submit_plan / get_plan / step_done / ask_user
│   ├── memory_tools.py       # ★ 新增：memory_search / memory_recall / memory_remember / memory_forget
│   └── ...（file_ops / system / todo_tools 保持）
├── memory/                   # ★ 升级为记忆子系统（原 memory.py 拆分）
│   ├── __init__.py           # 对外 API（兼容现有 save_conversation 等调用）
│   ├── store.py              # 持久化：原始会话 / 摘要 / 事实 / 画像 / 索引
│   ├── summarizer.py         # 总结器：会话结束总结 + 长会话增量滚动摘要
│   ├── extractor.py          # 抽取器：LLM 抽取事实/偏好 → 语义记忆
│   ├── retriever.py          # 检索器：关键词加权 Top-K（预留向量接口）
│   └── forget.py             # 遗忘器：时间衰减 / 容量上限 / 定期压缩
├── cli.py                    # run_ai_chat 接入 AgentLoop（lank ai 自动升级）
└── ...（config / model_config / utils / tui 保持）
```

### 依赖关系

```
cli ──→ agent.loop ──→ planner / executor / reviewer ──→ agent.prompts, agent.types
         │                      │
         │                      └──→ ai_client（底层 API 封装，保留）
         └──→ tools（注册表升级后复用 get_all_tools / execute_tool / needs_approval）
```

现有 `AIClient` 保留为底层封装：流式解析、工具调用循环机制可复用；Agent 框架在其上构建。

---

## 4. 核心数据模型（`agent/types.py`）

```python
class StepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"

@dataclass
class Step:
    id: int
    title: str                # 步骤描述
    action: str               # 要做什么（给 executor 的指令）
    tools_hint: List[str]     # 预计需要的工具（可选）
    acceptance: str           # 验收标准（review 用，关键字段）
    status: StepStatus = StepStatus.PENDING

@dataclass
class Plan:
    goal: str                 # 任务目标
    steps: List[Step]
    review_criteria: str      # 整体交付标准
    created_at: str
    status: PlanStatus        # created / confirmed / running / finished / abandoned

@dataclass
class ReviewVerdict:
    deliverable: bool
    summary: str              # 交付总结
    issues: List[str]         # 未达标项（对照验收标准逐条列出）
    new_steps: List[Step]     # 需要补做的步骤（成为新 todo）

class AgentPhase(str, Enum):
    CLASSIFY = "classify"
    PLAN = "plan"
    ACT = "act"
    REVIEW = "review"
    DONE = "done"
```

要点：

- **验收标准在规划阶段就定死**（`Step.acceptance` 与 `Plan.review_criteria`），review 阶段就是逐条核对，不是凭感觉自评；
- 计划结构与待办同构（可渲染为 `/todo` 风格列表），但独立存储，避免污染用户的全局待办。

---

## 5. 各阶段设计

### 5.1 分类（合并进规划，无独立往返）

**决策（已确认）**：工具调用式合并分类 + 规划。

实现方式：规划提示词（PLAN_PROMPT）指示 LLM——

- 若任务简单、可直接回答 → 直接输出文本，不调用任何工具；
- 若任务复杂 → 调用 `submit_plan(goal, steps, review_criteria)` 工具提交计划。

主循环检查首轮响应：

- 无工具调用 → 简单问答，直接交付；
- 调用 `submit_plan` → 进入 PLAN 阶段。

零额外往返，且利用原生 function calling 保证结构化输出。

### 5.2 PLAN 阶段（`planner.py`）

1. LLM 通过 `submit_plan` 提交计划（steps 每项必须带 `acceptance` 验收标准）；
2. 计划展示给用户，用户可：确认 / 修改步骤 / 取消（决策：默认确认，可配置 `/auto` 全自动）；
3. 确认后计划落为运行态，进入 ACT。

规划规则（写入 PLAN_PROMPT）：

- 每步只做一件事，步骤粒度以"可验收"为准；
- 信息不足时，规划一个 `ask_user` 步骤（向用户提问收集信息）或明确标注"需先获取的信息"；
- 步骤数上限（如 10 步），超出需合并。

### 5.3 ACT 阶段（`executor.py`）

**决策（已确认）**：每步独立紧凑上下文。

每步执行的上下文 = 系统提示词 + 目标 + 当前步骤（含验收标准）+ 前一步结果摘要 + 本轮新增消息。绝不复用整段会话历史。

执行流程：

1. 取下一个 PENDING 步骤；
2. 构建紧凑上下文，调用底层 chat（复用现有流式 + 工具循环机制）；
3. 该步内工具循环持续到：步骤验收标准达成（LLM 判定）或达到该步工具轮次上限；
4. 标记步骤 done（或 blocked，如用户取消 / 工具反复失败），记录该步结果摘要（供下一步与 review 使用）；
5. 全部步骤 done → 进入 REVIEW。

配套工具：

- `step_done(step_id, summary)`：步骤完成登记（LLM 调用）；
- `ask_user(question, options?)`：向用户提问并返回回答（信息收集步骤用），实现为阻塞式交互，由 UI 层回调；
- `get_plan()` / `get_step(step_id)`：查询当前计划与步骤（LLM 需要回顾时用）。

### 5.4 REVIEW 阶段（`reviewer.py`）

**决策（已确认）**：验收标准前置 + AI 自评 + 用户终审。

1. 构建审核上下文：goal + review_criteria + 各步 acceptance + 各步结果摘要 + 最终产物清单；
2. LLM 调用 `submit_review(deliverable, summary, issues, new_steps)` 提交结构化判定；
3. 判定为可交付 → 生成交付总结给用户，用户终审确认后结束；
4. 判定为未达标 → 将 `new_steps` 追加为计划新步骤（用户可见），回到 ACT；
5. 迭代上限 `MAX_REVIEW_ROUNDS`（默认 3）：超限仍未达标 → 停止并向用户说明现状与建议，交用户决定。

### 5.5 主循环（`loop.py`）

`AgentLoop` 状态机：

```python
class AgentLoop:
    def run(self, user_input) -> AgentResult: ...   # 一次完整 plan→act→review
```

- 持有：phase、当前 Plan、各步摘要、迭代计数；
- 控制：步骤上限、每步工具轮次上限、review 迭代上限、用户中断（Ctrl+C / 输入 no）；
- 事件回调：`on_plan_confirm`、`on_step_progress`、`on_review`、`on_ask_user`，由 UI 层（cli / tui）实现渲染；
- 非交互模式（`lank ai "..."` 单次调用、/auto）下自动确认计划、自动通过用户终审。

---

## 6. 系统提示词（`agent/prompts.py`）

三段提示词，均支持用户通过配置覆盖（`plan_prompt` / `exec_prompt` / `review_prompt`），基础层叠加工具描述与记忆注入（复用 `build_system_prompt` 机制，注入点详见第 8 节记忆系统）。

记忆注入按阶段分层：

- **分类/规划**：注入与目标相关的会话摘要 + 用户画像（「提前的加载」）；
- **执行**：默认不注入历史（保持每步紧凑上下文），需要时由 LLM 主动调用 `memory_search`；
- **review**：注入用户交付偏好（画像聚合摘要）。

### PLAN_PROMPT（含分类职责）

```
你是 LANK 的任务规划者。
- 如果用户请求简单、你可以直接回答，就直接回答，不要调用任何工具。
- 如果任务复杂（需要多步操作、多个工具、或需要收集信息），调用 submit_plan 提交计划。
计划要求：
- 每步只做一件事，粒度以"可验收"为准；
- 每一步必须写清：做什么(action)、预计工具(tools_hint)、验收标准(acceptance)；
- 信息不足时，规划 ask_user 步骤向用户提问，或明确标注需先获取的信息；
- 步骤不超过 10 步。
```

### EXEC_PROMPT（每步注入）

```
当前任务目标：{goal}
当前步骤（第 {i}/{n}）：{step.title}
本步要求：{step.action}
本步验收标准：{step.acceptance}
前一步结果摘要：{prev_summary}
请只完成当前步骤，达成验收标准后调用 step_done 登记，不要越步执行。
```

### REVIEW_PROMPT

```
任务目标：{goal}
整体交付标准：{review_criteria}
各步骤验收标准与结果：{steps_with_results}
请对照验收标准逐条核对，调用 submit_review 提交判定：
- deliverable=true 时给出交付总结 summary；
- deliverable=false 时必须给出具体 issues 与需要补做的 new_steps（每项同样带验收标准）。
```

---

## 7. 安全设计（todo.md 最重视项）

### 7.1 工具元数据升级（`tools/__init__.py`）

`register_tool` 新增字段：

```python
register_tool(
    name=...,
    description=...,
    func=...,
    parameters=...,
    # 新增：
    category="command",        # file / command / system / todo / plan / question
    danger_level=2,            # 0=只读 1=写文件 2=破坏性(删除/覆盖) 3=执行命令
    approval="confirm",        # "none" | "confirm" | "whitelist"
)
```

兼容旧调用（缺省：`category="misc"`、`danger_level=0`、`approval="confirm" if requires_approval else "none"`）。

### 7.2 命令执行重构（`cmd_exec.py`）

**决策（已确认）**：危险命令黑名单 + 参数化执行 + 输出截断。

- 去掉裸 `shell=True`：能参数化执行的命令改为参数列表方式执行；确需 shell 的命令（管道/重定向）走受控 shell，但仍过黑名单；
- **危险命令黑名单**（命中即拒绝并提示，不询问直接拦截）：
  - 删除类：`rm -rf`、`del /s /q`、`Remove-Item -Recurse -Force`、`rd /s /q`、`rmtree` 等；
  - 系统破坏类：`format`、`mkfs`、`fdisk`、`diskpart`、`shutdown`、`reboot`、`taskkill /f /im`、`reg delete`、清空环境变量、`> /dev/sda` 等；
  - 高危网络类（可配置）：`del` 之外的提权类、下载执行类（`curl|sh`、`iwr|iex`、`powershell -enc` 等）；
- **输出截断**：stdout/stderr 各截断（如 20KB），超长尾部省略并标注；
- 超时保留（60s，可配置）；
- 限制在 `working_dir` 内运行（`cwd` 约束）。

### 7.3 确认策略

- `approval="none"`：自动执行（只读类）；
- `approval="confirm"`：执行前询问（默认）；
- `approval="whitelist"`：查 `~/.lank/allowlist.json`，命中自动执行，否则询问；询问时可选择"本次会话放行 / 永久放行 / 拒绝"；
- `safe_mode=false` 时降级为全部自动执行（用户显式关闭，警告提示）。

---

## 8. 记忆系统

> 决策（已确认）：完整设计进本文档（四层记忆 + 流水线 + 记忆工具）；检索用 MVP 关键词加权、预留向量接口；总结时机为「会话结束 + 长会话增量」；画像为「自动抽取 + 显式记忆」并存。

### 8.1 现状评估（`memory.py`）

| 能力 | 现状 | 问题 |
|---|---|---|
| 会话历史存储 | ✅ 有 | 每会话只存最近 50 条原始消息 |
| 记忆注入 | ⚠️ 有 | `get_recent_context()` 是原始截断（最近 2 会话各 6 条、每条 100 字），无总结/相关性/重要性 |
| 用户画像 | ⚠️ 有壳 | `update_profile()` 全项目无调用方，画像永不自动更新 |
| 遗忘策略 | ⚠️ 半有 | `cleanup_old_memories()` 按天删文件但从未接入 |
| 检索 | ❌ 无 | 只能按时间倒序拿最近，不能按内容找相关 |

### 8.2 四层记忆架构

```
┌─────────────────────────────────────────────────┐
│  ① 工作记忆 Working Memory（会话/任务内）          │
│     当前 plan、当前步骤、步骤结果摘要、本轮上下文    │
│     —— 由 AgentLoop 管理，任务结束自动归档          │
├─────────────────────────────────────────────────┤
│  ② 情景记忆 Episodic（发生过什么）                 │
│     原始会话 + LLM 生成的会话摘要（最小记忆单元）     │
├─────────────────────────────────────────────────┤
│  ③ 语义记忆 Semantic（长期事实/偏好）              │
│     用户事实、偏好、项目知识、决策记录              │
│     —— LLM 自动抽取 + 显式记忆，去重冲突合并         │
├─────────────────────────────────────────────────┤
│  ④ 程序性记忆 Procedural（怎么做的，M7 后期）       │
│     用户习惯、工作流模式（"他总用 pip 装包"…）       │
└─────────────────────────────────────────────────┘
```

### 8.3 流水线（写 → 抽 → 索 → 取 → 忘）

```
每轮对话 / 会话结束
      │
      ▼
[总结器] LLM 增量滚动摘要（长会话按 token 阈值分片）
      │
      ▼
[抽取器] LLM 抽取新事实/偏好 → 语义记忆（去重、冲突合并）
      │
      ▼
[索引器] 关键词索引 + 时间戳 + 重要性分
      │
      ▼
[检索器] 注入时按 相关性×新鲜度×重要性 排序取 Top-K
      │
      ▼
[遗忘器] 时间衰减 + 容量上限 + 定期合并压缩
```

### 8.4 总结时机（决策）

- **会话结束时**：LLM 一次性生成会话摘要（`memory_summary_max_chars` 上限），摘要写入情景记忆，原始消息降级为可回溯存档；
- **长会话中途**：消息累计超过 `memory_long_session_threshold`（token 估算）时，触发增量滚动总结——对已积累片段分段压缩、合并，会话结束时只对"最后一段 + 合并摘要"再总结一次，防止长会话上下文失控。

### 8.5 画像写入（决策）

- **自动抽取**：每会话结束后 LLM 抽取新事实/偏好（"用户使用 Windows"、"偏好中文回复"、"项目 X 的技术栈"），写入语义记忆；
- **去重与冲突合并**：同主题新事实覆盖旧值并记录更新时间；置信度低的不写；
- **显式记忆**：`memory_remember(fact)` 工具供用户/AI 显式记忆，标记"显式"高置信、高重要性；
- `profile.json` 由语义记忆聚合生成，保持现有 `get_profile_summary()` 输出兼容（供 review 阶段注入交付偏好）。

### 8.6 检索器（MVP 关键词加权，决策）

```
score = relevance × w_relevance + freshness × w_freshness + importance × w_importance
```

- **relevance**：对 query 简单分词，命中摘要/事实/标题文本的关键词数占比；
- **freshness**：指数衰减 `1 / (1 + age_days × k)`，k 可配置；
- **importance**：显式记忆 > 自动抽取；提及次数多者高；含"偏好/决策/记住/重要"信号的加分；
- 按 `memory_top_k`（默认 5）注入，不同阶段注入不同记忆类型（见 8.8）；
- **预留向量接口**：`retriever` 提供抽象接口，M7 可无缝替换为本地向量嵌入（`fastembed`/`sentence-transformers`；DeepSeek 无 embedding API，云端向量不可行）。

### 8.7 记忆工具（LLM 可调用，`memory_tools.py`）

| 工具 | 作用 | danger_level / approval |
|---|---|---|
| `memory_search(query)` | 检索相关历史/摘要/事实（RAG 风格主动调用） | 0 / none |
| `memory_recall(topic)` | 召回某主题的长期事实 | 0 / none |
| `memory_remember(fact, importance?)` | 显式记忆 | 1 / confirm |
| `memory_forget(key)` | 删除/标记遗忘 | 2 / confirm |

### 8.8 与 ReAct 框架的注入点

- **分类/规划**：注入与目标相关的会话摘要 + 用户画像（「提前的加载」）；
- **执行**：默认不注入历史（保持每步紧凑上下文），需要时 LLM 主动调 `memory_search`；
- **review**：注入用户交付偏好（`profile.json` 聚合摘要）；
- **工作记忆**（当前 plan/步骤/结果摘要）由 AgentLoop 管理，任务结束归档为情景记忆。

### 8.9 「提前的加载」落地（todo.md 原话）

- **会话启动**：加载画像摘要 + 最近 2 个会话摘要（替代现有 `get_recent_context` 的原始截断注入）；
- **任务检测**：进入 PLAN 前用 goal 关键词预检索相关旧会话，作为规划上下文，让 AI 在拆解任务时就"记得"相关过往。

### 8.10 数据存储布局

```
~/.lank/memory/
├── history/           # 原始会话（保留，回溯用）
├── summaries.json     # 情景记忆：会话摘要（LLM 生成）
├── facts.json         # 语义记忆：事实/偏好（来源、时间、置信度、重要性）
├── profile.json       # 用户画像（由 facts 聚合，兼容现有）
└── index.json         # 关键词索引（可重建）
```

> 兼容：现有 `memory.py` 对外函数（`save_conversation` / `get_recent_context` / `get_profile_summary` 等）在升级为 `memory/` 包后保持同名导出，`ai_client._build_system_prompt` 等既有调用方不受影响。

---

## 9. 上下文管理（根治 400 报错）

1. **会话滑动窗口**：`run_ai_chat` 的 `history` 按 `max_history`（默认 100 条）滑动裁剪，最长会话不再无限增长；
2. **工具结果截断**：`execute_tool` 返回内容在进入 messages 前按字符上限（如 8KB）截断，超长保留头部并标注省略；
3. **每步紧凑上下文**：ACT 阶段绝不携带整段历史，只带目标 + 当前步 + 前步摘要（核心手段）；
4. **阶段摘要**：每步完成后生成 ≤N 字的结构化摘要，供下一步与 review 使用，原始轮次消息不保留到下一步；
5. 后期（M7）：上下文压缩 tool，分情况策略（长会话摘要压缩 / 工具结果滚动压缩 / 记忆层压缩）。

---

## 10. 配置新增（`config.py` 默认值草案）

```python
"auto_mode": False,             # True 时计划自动确认、review 自动通过（全自动）
"max_plan_steps": 10,           # 单计划最大步骤数
"max_review_rounds": 3,         # review 未达标最大迭代轮数
"plan_prompt": "",              # 覆盖 PLAN_PROMPT
"exec_prompt": "",              # 覆盖 EXEC_PROMPT
"review_prompt": "",            # 覆盖 REVIEW_PROMPT
"tool_output_limit": 8192,      # 工具结果截断字符数
"cmd_output_limit": 20480,      # 命令输出截断字符数
"cmd_timeout": 60,              # 命令超时秒数
"cmd_allowlist": [],            # 命令白名单（可自动执行）
# ── 记忆系统 ──
"memory_summary_max_chars": 2000,         # 会话摘要长度上限
"memory_long_session_threshold": 20000,   # 触发长会话增量总结的 token 阈值
"memory_top_k": 5,                        # 检索注入条数
"memory_relevance_weight": 0.4,           # 检索权重：相关性
"memory_freshness_weight": 0.3,           # 检索权重：新鲜度
"memory_importance_weight": 0.3,          # 检索权重：重要性
"memory_max_facts": 200,                  # 语义记忆容量上限
"memory_auto_extract": True,              # 会话后自动抽取画像
```

---

## 11. 额外优化清单

> 决策（已确认）：全部入档；M0 扩为含代码级 Bug 与健壮性修复。

### 11.1 代码级 Bug（P0，M0 修）

| # | 问题 | 位置 | 修法 |
|---|---|---|---|
| 1 | todo id 重复：`todo_add` 用 `len(todos)+1` 生成 id，删除后新增会冲突 | `tools/todo_tools.py` | 改为 `max(id)+1`（或自增计数器） |
| 2 | 命令执行目录与文件操作不一致：`cmd_exec` 用 `os.getcwd()`，`file_ops` 用 `get_working_dir()` | `tools/cmd_exec.py` | 统一为 `get_working_dir()` |
| 3 | `calculate` 可被 DoS：字符集未禁 `**` 幂运算，`9**9**9**9` 打满 CPU/内存 | `tools/system.py` | 表达式长度上限 + 禁用 `**` + 结果上限检查 |
| 4 | 会话文件秒级冲突：`save_conversation` 用 `%Y%m%d_%H%M%S` 命名 | `memory.py` | 命名加随机后缀或递增序号 |
| 5 | 版本号硬编码：`print_help` 写死 `v0.2.0`，与 `__version__` 不同步 | `cli.py` | 统一引用 `__version__` |

### 11.2 健壮性 / 性能（P1，M0 修）

| # | 问题 | 修法 |
|---|---|---|
| 6 | 配置读取无缓存：`get_config()` 每次全量读盘 + JSON 解析 | 进程级缓存 + `set_config` 时失效 |
| 7 | tool_call 参数 JSON 解析失败静默降级为 `{}`（两处） | 记录警告并反馈给模型，不静默 |
| 8 | 工具参数无 schema 校验：`execute_tool` 直接 `func(**arguments)` | 轻量手动校验（类型/必填），错误信息友好 |
| 9 | JSON 持久化无原子写（config/todos/stats） | 写临时文件 + `os.replace` |
| 10 | 无日志系统，全部 `print` | 引入 `logging`，工具调用/错误落日志文件 |
| 11 | 无 429/5xx 退避重试 | 请求层指数退避，重试上限可配置 |

### 11.3 体验 / 架构（P2，随框架重构吸收）

| # | 问题 | 说明 |
|---|---|---|
| 12 | TUI 与 CLI 的 AI 回调逻辑重复（两套 on_tool_call/on_text） | AgentLoop 落地后收敛为共享层 |
| 13 | `run_ai_chat` 340 行巨型函数，命令 if-elif 堆叠 | 命令表驱动（dict 分发）重构 |
| 14 | `/resume` 缺失：`load_conversation` 无入口 | 支持恢复上次会话 |
| 15 | 无 token 用量统计：`usage` 字段被丢弃 | `/stats` 增加 token/成本统计 |
| 16 | CLI 的 `input()` 无多行/粘贴体验 | 迁移到 prompt_toolkit 输入 |

### 11.4 工程化（P2/P3）

- **零测试**：增加 pytest 冒烟层（工具注册、配置合并、记忆读写）
- **无 lint 配置**：引入 ruff
- **`simple_chat` 死代码**：删除或接线

---

## 12. 实施里程碑

| 里程碑 | 内容 | 验收 |
|---|---|---|
| **M0 地基（扩）** | 上下文管理（滑动窗口 + 结果截断）+ `execute_command` 安全重构 + 代码级 Bug（优化清单 #1–#5）+ 健壮性（#6/#7/#9/#10/#11：配置缓存、原子写、日志、重试） | 长会话不再 400；危险命令被拦截；todo id 不冲突；calculate 拒幂运算；配置有缓存；持久化原子写；日志落地 |
| **M1 骨架** | `agent/types.py` + `prompts.py` + `AgentLoop` 状态机空跑 | plan→act→review 全链路可空跑、可中断 |
| **M2 规划** | `submit_plan` 工具 + 计划展示与确认 | 复杂任务自动拆解，用户可确认/修改 |
| **M3 执行** | `executor` 每步紧凑上下文 + 步验收 + `ask_user` | 多步任务按计划逐步执行，每步独立上下文 |
| **M4 审核** | `reviewer` 验收对照 + 自动迭代（限 N 轮） | 未达标自动补步骤重跑，可交付才总结 |
| **M5 记忆系统** | `memory/` 包：总结器（会话结束 + 长会话增量）+ 抽取器（自动画像）+ 检索器（关键词加权）+ 遗忘器 + memory 工具 + 注入点接入 | 长会话有滚动摘要；画像自动更新；`memory_search` 可用；「提前的加载」生效 |
| **M6 接入** | `cli.py` 接入 AgentLoop + 新配置项 + TUI 同步 | `lank ai` 全面升级，`lank tui` 同步可用 |
| **M7 后期** | 上下文压缩 tool、向量检索（fastembed）、程序性记忆、AI 桌宠（todo.md 后续项） | 另立设计 |

每阶段独立可验收；M0 不依赖框架，可先行落地。

---

## 13. 决策记录

| 日期 | 决策点 | 结论 |
|---|---|---|
| 2025 | 分类策略 | 工具调用式合并分类 + 规划（LLM 直接回答 or submit_plan），零额外往返 |
| 2025 | 计划确认 | 默认展示计划等用户确认，可配置 `/auto` 全自动 |
| 2025 | 执行上下文 | 每步独立紧凑上下文（目标+当前步+前步摘要） |
| 2025 | 命令安全 | 危险命令黑名单 + 参数化执行 + 输出截断，其余维持确认 |
| 2025 | 交付审核 | 验收标准前置 + AI 逐条自评 + 用户终审 |
| 2025 | 推进方式 | 先写本文档定稿，确认后再动代码 |
| 2025 | 记忆范围 | 四层记忆（工作/情景/语义/程序）+ 流水线 + 记忆工具，完整补进本文档 |
| 2025 | 记忆检索 | MVP 关键词加权（相关性×新鲜度×重要性）Top-K，预留向量接口后期替换 |
| 2025 | 总结时机 | 会话结束一次性总结 + 长会话按 token 阈值增量滚动总结 |
| 2025 | 画像写入 | LLM 自动抽取（去重/冲突合并）+ `memory_remember` 显式记忆并存 |
| 2025 | 额外优化 | 代码级 Bug + 健壮性 + 体验 + 工程化全部入档（第 11 节） |
| 2025 | M0 范围 | 扩为：上下文管理 + 命令安全 + 代码级 Bug + 健壮性 |
