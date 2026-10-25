# LANK 待办清单

## 框架结构 ReAct ✅ v0.3.0 已实现（docs/design.md 定稿）

- [x] 先拿到用户内容
    - [x] 简单问答内容，直接回答
    - [x] 复杂业务
        - [x] plan 模式：`agent/planner.py` 拆解任务为带验收标准的步骤计划，用户确认后执行（`/auto` 可全自动）
        - [x] act 模式：`agent/executor.py` 每步独立紧凑上下文，逐步调用工具完成任务
        - [x] review 模式：`agent/reviewer.py` 对照验收标准审核是否可交付
            - [x] 可交付 -> 直接总结交付（用户终审）
            - [x] 未达到预期 -> 制定新步骤（new_steps）自动迭代重跑（最多 max_review_rounds 轮）
- [x] 系统提示词完善：PLAN/EXEC/REVIEW 三段提示词（`agent/prompts.py`），支持 `plan_prompt`/`exec_prompt`/`review_prompt` 配置覆盖

## 后期

- [x] 记忆系统 v0.3.0 基础版：会话滚动摘要 + 自动画像抽取 + 关键词加权检索（`lank/memory/`）
- [x] 上下文压缩：工具/命令输出截断改首尾保留式 smart_truncate（保尾部结论）、记忆注入预算封顶（memory_max_inject_chars）、单步字符预算护栏（max_step_context_chars）、token 用量增量落盘（/stats 可观测）
- [x] 向量检索（`memory/vector.py`，fastembed 本地 ONNX、零网络 API）：默认关闭（memory_vector_enabled），未安装/失败静默降级关键词路径；DeepSeek 无 embedding API，故走本地后端
- [x] 程序性记忆（`procedures.json`）：任务成功后自动沉淀可复用工作流，规划阶段按相关性注入（memory_procedural_enabled / memory_procedure_top_k），/memory 可查看管理

## 已修复（v0.3.0）

- [x] 400 上下文爆炸：会话滑动窗口（max_history）+ 工具结果截断（tool_output_limit）+ 每步紧凑上下文
- [x] 调用工具的安全：命令执行危险命令黑名单 + 输出截断 + 白名单（allowlist.json）+ 参数化执行（非 Windows）
- [x] todo id 删除后重复、calculate 幂运算 DoS、会话文件秒级冲突、版本号硬编码
- [x] 配置读取缓存、JSON 原子写、日志系统、API 429/5xx 退避重试、工具参数校验
- [x] **输入框固定底部**：`lank tui` / `lank ai` 重写为 prompt_toolkit 全屏聊天界面，
      输入框钉在屏幕最底部、消息内容向上滚动堆积，`PageUp`/`PageDown` 回看历史，不再清屏闪烁
- [x] **流式 token 统计恒 0**：`_create_completion` 流式请求补 `stream_options={"include_usage": True}`（不传则流式 chunk 不带 usage，纯对话路径 /stats 失真）；兼容供应商不认此参数时自动降级重试
- [x] **终端日志开关误伤日志文件**：`set_console_logging` 原用 isinstance(StreamHandler) 匹配，连带命中 RotatingFileHandler → 改为只精准调整 stderr handler
- [x] **可配置提示词崩溃**：exec/review 模板原用 str.format() 渲染，用户自定义提示词含字面 `{ }`（代码/JSON 示例）即抛异常炸掉整个任务 → 改 `_render()` 只替换已知占位符
- [x] **TUI 总结线程数据竞争**：守护线程改收历史快照，不再持有 live `ai_history` 引用；防重登记集合改有界 LRU
- [x] **doctor 短 Key 脱敏**：`lank doctor` 对短 API Key 不再拼前后缀（几乎外泄全文），长 Key 只露首4末2

## 后续计划

- AI 桌宠发展，环境意识，自主生活，荒地开垦
