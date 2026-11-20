from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Any
from uuid import UUID, uuid4


class TaskType(str, Enum):
    BACKTEST = "BACKTEST"
    STRATEGY_OPTIMIZATION = "STRATEGY_OPTIMIZATION"
    TECHNICAL_ANALYSIS = "TECHNICAL_ANALYSIS"
    AI_ANALYSIS = "AI_ANALYSIS"
    PORTFOLIO_ANALYSIS = "PORTFOLIO_ANALYSIS"


class TaskPriority(IntEnum):
    LOW = 1
    NORMAL = 5
    HIGH = 8
    CRITICAL = 10


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_STATUSES = {
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class Task:
    task_type: TaskType
    priority: TaskPriority = TaskPriority.NORMAL
    payload: Any = field(default=None, repr=False)
    metadata: dict[str, Any] = field(default_factory=dict)
    task_id: UUID = field(default_factory=uuid4)
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: Any = None
    error: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.task_type, TaskType):
            self.task_type = TaskType(self.task_type)
        if not isinstance(self.priority, TaskPriority):
            self.priority = TaskPriority(self.priority)
        if not isinstance(self.metadata, dict):
            raise TypeError("metadata must be a dictionary.")
        estimate = self.metadata.get("estimated_memory_mb")
        if estimate is not None and (
            isinstance(estimate, bool)
            or not isinstance(estimate, int)
            or estimate < 1
        ):
            raise ValueError("estimated_memory_mb must be a positive integer.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": str(self.task_id),
            "task_type": self.task_type.value,
            "priority": int(self.priority),
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": (
                self.started_at.isoformat() if self.started_at else None
            ),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata.copy(),
        }
