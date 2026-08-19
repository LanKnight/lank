"""
agent/types.py - ReAct 框架数据模型（design.md §4）

验收标准前置：Step.acceptance 与 Plan.review_criteria 在规划阶段定死，
review 阶段逐条对照。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class StepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"


class PlanStatus(str, Enum):
    CREATED = "created"
    CONFIRMED = "confirmed"
    RUNNING = "running"
    FINISHED = "finished"
    ABANDONED = "abandoned"


@dataclass
class Step:
    id: int
    title: str                 # 步骤描述
    action: str                # 要做什么（给 executor 的指令）
    acceptance: str            # 验收标准（review 用，关键字段）
    tools_hint: List[str] = field(default_factory=list)  # 预计需要的工具
    status: StepStatus = StepStatus.PENDING
    summary: str = ""          # 步骤结果摘要（执行后填充）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "action": self.action,
            "acceptance": self.acceptance,
            "tools_hint": list(self.tools_hint),
            "status": self.status.value,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Step":
        return cls(
            id=int(data.get("id", 0)),
            title=data.get("title", ""),
            action=data.get("action", ""),
            acceptance=data.get("acceptance", ""),
            tools_hint=list(data.get("tools_hint", [])),
            status=StepStatus(data.get("status", "pending")),
            summary=data.get("summary", ""),
        )


@dataclass
class Plan:
    goal: str
    steps: List[Step]
    review_criteria: str = ""
    created_at: str = ""
    status: PlanStatus = PlanStatus.CREATED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "review_criteria": self.review_criteria,
            "created_at": self.created_at,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Plan":
        return cls(
            goal=data.get("goal", ""),
            steps=[Step.from_dict(s) for s in data.get("steps", [])],
            review_criteria=data.get("review_criteria", ""),
            created_at=data.get("created_at", ""),
            status=PlanStatus(data.get("status", "created")),
        )


@dataclass
class ReviewVerdict:
    deliverable: bool
    summary: str = ""                     # 交付总结
    issues: List[str] = field(default_factory=list)     # 未达标项
    new_steps: List[Step] = field(default_factory=list) # 需要补做的步骤


class AgentPhase(str, Enum):
    CLASSIFY = "classify"
    PLAN = "plan"
    ACT = "act"
    REVIEW = "review"
    DONE = "done"


@dataclass
class AgentResult:
    """一次 AgentLoop.run() 的结果"""
    success: bool
    response: str                          # 最终交付文本或错误信息
    phase: AgentPhase = AgentPhase.DONE
    plan: Optional[Plan] = None            # 本次任务使用的计划（若有）


def render_plan_text(plan: Plan) -> str:
    """将计划渲染为可读文本（供 UI 展示）"""
    lines = [
        f"🎯 任务目标: {plan.goal}",
        "",
        f"📋 执行计划（{len(plan.steps)} 步）:",
    ]
    for i, step in enumerate(plan.steps, 1):
        icon = {StepStatus.DONE: "✅", StepStatus.IN_PROGRESS: "⏳",
                StepStatus.BLOCKED: "⛔"}.get(step.status, "⬜")
        lines.append(f"  {icon} [{i}] {step.title}")
        if step.acceptance:
            lines.append(f"       验收: {step.acceptance}")
        if step.status == StepStatus.DONE and step.summary:
            lines.append(f"       结果: {step.summary[:80]}")
    if plan.review_criteria:
        lines.append(f"\n📐 整体交付标准: {plan.review_criteria}")
    return "\n".join(lines)
