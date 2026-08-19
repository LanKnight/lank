"""
计划工具 - ReAct 框架专用（design.md §5.2/§5.3/§5.4）
submit_plan / get_plan / step_done / ask_user / submit_review

这些工具通过 agent.context 与运行中的 AgentLoop 通信。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from ..agent.context import get_current_loop
from ..agent.types import Plan, ReviewVerdict, Step, StepStatus, render_plan_text
from ..logs import get_logger
from . import register_tool

logger = get_logger("plan_tools")


def submit_plan(goal: str, steps: List[Dict[str, Any]], review_criteria: str = "") -> str:
    """提交执行计划（PLAN 阶段由模型调用）"""
    loop = get_current_loop()
    if loop is None:
        return "错误: 当前没有运行中的任务循环"
    if not goal or not steps:
        return "错误: 计划必须包含目标与至少一个步骤"

    plan_steps = []
    for i, s in enumerate(steps, 1):
        if not isinstance(s, dict):
            continue
        plan_steps.append(Step(
            id=i,
            title=str(s.get("title", "")),
            action=str(s.get("action", "")),
            acceptance=str(s.get("acceptance", "")),
            tools_hint=[str(t) for t in (s.get("tools_hint") or [])],
        ))

    if not plan_steps:
        return "错误: 计划步骤为空，请至少提供一个有效步骤"

    plan = Plan(
        goal=goal,
        steps=plan_steps,
        review_criteria=review_criteria,
        created_at=datetime.now().isoformat(),
    )
    loop._pending_plan = plan
    logger.info("收到计划: %s (%d 步)", goal, len(plan_steps))
    return f"计划已提交（{len(plan_steps)} 步）"


def get_plan() -> str:
    """查看当前执行计划"""
    loop = get_current_loop()
    if loop is None or loop.plan is None:
        return "当前没有正在执行的计划"
    return render_plan_text(loop.plan)


def step_done(step_id: int, summary: str = "") -> str:
    """登记当前步骤已完成（ACT 阶段由模型调用）"""
    loop = get_current_loop()
    if loop is None or loop.plan is None:
        return "错误: 当前没有运行中的任务"
    for step in loop.plan.steps:
        if step.id == int(step_id):
            step.status = StepStatus.DONE
            step.summary = summary
            logger.info("步骤完成: #%d %s", step.id, summary[:100])
            return f"✅ 步骤 #{step.id} 已完成"
    return f"错误: 未找到步骤 #{step_id}"


def ask_user(question: str, options: Optional[List[str]] = None) -> str:
    """向用户提问并获取回答（信息收集步骤用）"""
    loop = get_current_loop()
    if loop is None or loop.callbacks is None or loop.callbacks.on_ask_user is None:
        return "（无法向用户提问：当前环境不支持交互）"
    return loop.callbacks.on_ask_user(question, options or [])


def submit_review(
    deliverable: bool,
    summary: str = "",
    issues: Optional[List[str]] = None,
    new_steps: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """提交审核判定（REVIEW 阶段由模型调用）"""
    loop = get_current_loop()
    if loop is None:
        return "错误: 当前没有运行中的任务"

    steps: List[Step] = []
    for s in new_steps or []:
        if not isinstance(s, dict):
            continue
        steps.append(Step(
            id=loop._next_step_id(),
            title=str(s.get("title", "")),
            action=str(s.get("action", "")),
            acceptance=str(s.get("acceptance", "")),
        ))

    loop._pending_verdict = ReviewVerdict(
        deliverable=bool(deliverable),
        summary=str(summary),
        issues=list(issues or []),
        new_steps=steps,
    )
    return "审核判定已提交"


# ── 注册工具 ──

register_tool(
    name="submit_plan",
    description="提交任务执行计划（复杂任务规划时调用）",
    func=submit_plan,
    parameters=[
        {"name": "goal", "type": "string", "description": "任务目标"},
        {"name": "steps", "type": "array", "description": "步骤列表，每项含 title/action/acceptance/tools_hint"},
        {"name": "review_criteria", "type": "string", "description": "整体交付标准", "required": False},
    ],
    category="plan",
    danger_level=0,
)

register_tool(
    name="get_plan",
    description="查看当前执行计划",
    func=get_plan,
    parameters=[],
    category="plan",
    danger_level=0,
)

register_tool(
    name="step_done",
    description="登记当前步骤已完成（含结果摘要）",
    func=step_done,
    parameters=[
        {"name": "step_id", "type": "integer", "description": "步骤编号"},
        {"name": "summary", "type": "string", "description": "步骤完成情况摘要", "required": False},
    ],
    category="plan",
    danger_level=0,
)

register_tool(
    name="ask_user",
    description="向用户提问并获取回答（需要收集信息时用）",
    func=ask_user,
    parameters=[
        {"name": "question", "type": "string", "description": "要问的问题"},
        {"name": "options", "type": "array", "description": "可选答案列表", "required": False},
    ],
    category="question",
    danger_level=0,
)

register_tool(
    name="submit_review",
    description="提交交付审核判定",
    func=submit_review,
    parameters=[
        {"name": "deliverable", "type": "boolean", "description": "是否可交付"},
        {"name": "summary", "type": "string", "description": "交付总结", "required": False},
        {"name": "issues", "type": "array", "description": "未达标问题列表", "required": False},
        {"name": "new_steps", "type": "array", "description": "需补做的步骤列表", "required": False},
    ],
    category="plan",
    danger_level=0,
)
