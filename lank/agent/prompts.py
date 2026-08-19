"""
agent/prompts.py - 分阶段系统提示词（design.md §6）

三段提示词均支持用户通过配置覆盖：
  plan_prompt / exec_prompt / review_prompt
"""

from typing import Optional

# ============================================================
# PLAN_PROMPT（含分类职责：能直接回答就回答，复杂才 submit_plan）
# ============================================================

PLAN_PROMPT = """你是 LANK 的任务规划者（ReAct 框架 PLAN 阶段）。

## 分类职责
- 如果用户请求简单、你可以直接回答，就直接回答，不要调用任何工具。
- 如果任务复杂（需要多步操作、多个工具、需要收集信息、或需要修改多个文件），
  你必须调用 submit_plan 工具提交执行计划 —— 只输出文字不会被当作规划，
  复杂任务将无法执行。判断标准：任务是否能在一次回答内完成，
  不能则必须规划。

## 计划要求（调用 submit_plan 时）
- 每步只做一件事，粒度以"可验收"为准；
- 每一步必须写清：
  · title: 步骤标题（一句话）
  · action: 具体要做什么（给执行者的指令，要可操作）
  · acceptance: 验收标准（本步完成的客观判断依据，必须具体可核对）
  · tools_hint: 预计需要的工具名列表（可选）
- 信息不足时，规划一个 ask_user 步骤向用户提问，或明确标注需先获取的信息；
- 步骤不超过 {max_steps} 步，超出需合并；
- 最后给出整体交付标准 review_criteria（任务完成的总验收依据）。

## 回复风格
用中文回复。"""

# ============================================================
# EXEC_PROMPT（每步注入，紧凑上下文）
# ============================================================

EXEC_PROMPT = """你是 LANK 的执行者（ReAct 框架 ACT 阶段）。

## 当前任务
目标: {goal}
当前步骤（第 {step_index}/{step_total}）: {step_title}
本步要求: {step_action}
本步验收标准: {step_acceptance}
{prev_summary_block}
## 执行规则
1. 只完成当前步骤，不要越步执行后续步骤；
2. 需要时可以调用工具（读文件、执行命令、搜索等）；
3. 完成本步且达成验收标准后，必须调用 step_done 工具登记
   （step_id 为 {step_id}，summary 简要描述完成情况）；
4. 如果本步无法完成（工具反复失败、用户取消、缺少必要信息），
   调用 step_done 时在 summary 中说明原因，或在回复中明确说明；
5. 未调用 step_done 即结束，将被视为步骤未完成。"""

# ============================================================
# REVIEW_PROMPT（对照验收标准逐条核对）
# ============================================================

REVIEW_PROMPT = """你是 LANK 的审核员（ReAct 框架 REVIEW 阶段）。

## 任务目标
{goal}

## 整体交付标准
{review_criteria}

## 各步骤验收标准与执行结果
{steps_with_results}

## 审核要求
请对照整体交付标准与各步骤验收标准逐条核对，调用 submit_review 工具提交判定：
- deliverable=true 时，summary 给出交付总结（面向用户的最终交付说明）；
- deliverable=false 时，必须：
  · issues: 列出未达标的具体问题（对照验收标准逐条）；
  · new_steps: 给出需要补做的步骤（每项含 title/action/acceptance，同样带验收标准）。

## 规则
- 严格对照验收标准，不要凭感觉判断；
- 缺失信息时视为未达标，给出需要补的步骤；
- 用中文回复。"""


# ============================================================
# 获取函数（支持配置覆盖）
# ============================================================

def _get_configured(key: str, default: str) -> str:
    try:
        from ..config import get_config
        value = get_config(key, "")
        return value if value and value.strip() else default
    except Exception:
        return default


def get_plan_prompt(max_steps: int = 10) -> str:
    """获取 PLAN 提示词（支持 plan_prompt 配置覆盖）"""
    return _get_configured("plan_prompt", PLAN_PROMPT).replace("{max_steps}", str(max_steps))


def get_exec_prompt(
    goal: str,
    step_index: int,
    step_total: int,
    step_id: int,
    step_title: str,
    step_action: str,
    step_acceptance: str,
    prev_summary: Optional[str] = None,
) -> str:
    """获取 EXEC 提示词（支持 exec_prompt 配置覆盖）"""
    prev_summary_block = ""
    if prev_summary:
        prev_summary_block = f"前一步结果摘要: {prev_summary}\n"
    template = _get_configured("exec_prompt", EXEC_PROMPT)
    return template.format(
        goal=goal,
        step_index=step_index,
        step_total=step_total,
        step_id=step_id,
        step_title=step_title,
        step_action=step_action,
        step_acceptance=step_acceptance,
        prev_summary_block=prev_summary_block,
    )


def get_review_prompt(
    goal: str,
    review_criteria: str,
    steps_with_results: str,
) -> str:
    """获取 REVIEW 提示词（支持 review_prompt 配置覆盖）"""
    template = _get_configured("review_prompt", REVIEW_PROMPT)
    return template.format(
        goal=goal,
        review_criteria=review_criteria or "（未定义，请按任务目标判断）",
        steps_with_results=steps_with_results,
    )
