from dataclasses import asdict, dataclass
from typing import Any

import psutil

from config.computing import COMPUTING_SETTINGS, ComputingSettings
from computing.models import TaskType


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    cpu_percent: float
    memory_percent: float
    memory_available_bytes: int
    memory_total_bytes: int
    cpu_count: int
    active_cpu_workers: int
    active_llm_requests: int
    active_tasks: int
    max_cpu_workers: int
    max_llm_parallel: int
    max_total_tasks: int
    max_memory_usage_percent: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResourceManager:
    """Reads host resources and applies conservative admission control."""

    CPU_TASK_TYPES = {
        TaskType.BACKTEST,
        TaskType.STRATEGY_OPTIMIZATION,
        TaskType.TECHNICAL_ANALYSIS,
        TaskType.PORTFOLIO_ANALYSIS,
    }
    HEAVY_TASK_TYPES = {
        TaskType.BACKTEST,
        TaskType.STRATEGY_OPTIMIZATION,
    }

    def __init__(self, settings: ComputingSettings = COMPUTING_SETTINGS):
        self.settings = settings

    def estimate_task_memory_mb(
        self,
        task_type: TaskType,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Return a conservative reservation; callers may provide an estimate."""
        metadata = metadata or {}
        estimate = metadata.get("estimated_memory_mb")
        if estimate is not None:
            if (
                isinstance(estimate, bool)
                or not isinstance(estimate, int)
                or estimate < 1
            ):
                raise ValueError("estimated_memory_mb must be a positive integer.")
            return estimate
        if task_type in self.HEAVY_TASK_TYPES:
            return self.settings.heavy_cpu_task_memory_mb
        if task_type is TaskType.AI_ANALYSIS:
            return self.settings.llm_task_memory_mb
        return self.settings.default_cpu_task_memory_mb

    def get_snapshot(
        self,
        active_cpu_workers: int = 0,
        active_llm_requests: int = 0,
        active_tasks: int = 0,
    ) -> ResourceSnapshot:
        memory = psutil.virtual_memory()
        return ResourceSnapshot(
            cpu_percent=float(psutil.cpu_percent(interval=None)),
            memory_percent=float(memory.percent),
            memory_available_bytes=int(memory.available),
            memory_total_bytes=int(memory.total),
            cpu_count=int(psutil.cpu_count(logical=True) or 1),
            active_cpu_workers=active_cpu_workers,
            active_llm_requests=active_llm_requests,
            active_tasks=active_tasks,
            max_cpu_workers=self.settings.max_cpu_workers,
            max_llm_parallel=self.settings.max_llm_parallel,
            max_total_tasks=self.settings.max_total_tasks,
            max_memory_usage_percent=self.settings.max_memory_usage_percent,
        )

    def can_start(
        self,
        task_type: TaskType,
        active_cpu_workers: int,
        active_llm_requests: int,
        active_tasks: int,
        task_metadata: dict[str, Any] | None = None,
        active_reserved_memory_mb: int = 0,
    ) -> bool:
        if active_tasks >= self.settings.max_total_tasks:
            return False

        snapshot = self.get_snapshot(
            active_cpu_workers=active_cpu_workers,
            active_llm_requests=active_llm_requests,
            active_tasks=active_tasks,
        )
        if snapshot.memory_percent >= self.settings.max_memory_usage_percent:
            return False

        memory_budget = (
            snapshot.memory_total_bytes
            * self.settings.max_memory_usage_percent
            / 100
        )
        memory_in_use = snapshot.memory_total_bytes - snapshot.memory_available_bytes
        reserved = active_reserved_memory_mb * 1024 * 1024
        incoming = (
            self.estimate_task_memory_mb(task_type, task_metadata)
            * 1024
            * 1024
        )
        if memory_budget - memory_in_use - reserved < incoming:
            return False

        if task_type in self.CPU_TASK_TYPES:
            return (
                active_cpu_workers < self.settings.max_cpu_workers
                and snapshot.cpu_percent < self.settings.max_cpu_usage_percent
            )

        if task_type is TaskType.AI_ANALYSIS:
            return active_llm_requests < self.settings.max_llm_parallel

        return False
