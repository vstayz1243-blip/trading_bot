import math
import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ComputingSettings:
    """Resource limits for the local computing core."""

    max_cpu_workers: int = 2
    max_llm_parallel: int = 2
    max_total_tasks: int = 4
    max_memory_usage_percent: float = 80.0
    max_cpu_usage_percent: float = 95.0
    default_cpu_task_memory_mb: int = 256
    heavy_cpu_task_memory_mb: int = 2048
    llm_task_memory_mb: int = 512
    resource_check_interval: float = 0.5
    ollama_timeout: float = 300.0
    llm_retries: int = 1

    def __post_init__(self) -> None:
        integer_fields = (
            "max_cpu_workers",
            "max_llm_parallel",
            "max_total_tasks",
            "default_cpu_task_memory_mb",
            "heavy_cpu_task_memory_mb",
            "llm_task_memory_mb",
        )
        for name in integer_fields:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer.")

        for name in ("max_memory_usage_percent", "max_cpu_usage_percent"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a number.")
            if not math.isfinite(value) or not 0 < value <= 100:
                raise ValueError(f"{name} must be between 0 and 100.")

        if self.max_cpu_workers > self.max_total_tasks:
            raise ValueError("max_cpu_workers cannot exceed max_total_tasks.")
        if self.max_llm_parallel > self.max_total_tasks:
            raise ValueError("max_llm_parallel cannot exceed max_total_tasks.")
        if (
            isinstance(self.resource_check_interval, bool)
            or not isinstance(self.resource_check_interval, (int, float))
            or not math.isfinite(self.resource_check_interval)
            or self.resource_check_interval <= 0
        ):
            raise ValueError("resource_check_interval must be positive and finite.")
        if (
            isinstance(self.ollama_timeout, bool)
            or not isinstance(self.ollama_timeout, (int, float))
            or not math.isfinite(self.ollama_timeout)
            or self.ollama_timeout <= 0
        ):
            raise ValueError("ollama_timeout must be positive and finite.")
        if (
            isinstance(self.llm_retries, bool)
            or not isinstance(self.llm_retries, int)
            or self.llm_retries < 0
        ):
            raise ValueError("llm_retries must be a non-negative integer.")

    @classmethod
    def from_env(cls) -> "ComputingSettings":
        """Load optional overrides without changing trading risk settings."""
        return cls(
            max_cpu_workers=int(os.getenv("MAX_CPU_WORKERS", "2")),
            max_llm_parallel=int(os.getenv("MAX_LLM_PARALLEL", "2")),
            max_total_tasks=int(os.getenv("MAX_TOTAL_TASKS", "4")),
            max_memory_usage_percent=float(
                os.getenv("MAX_MEMORY_USAGE_PERCENT", "80")
            ),
            max_cpu_usage_percent=float(
                os.getenv("MAX_CPU_USAGE_PERCENT", "95")
            ),
            default_cpu_task_memory_mb=int(
                os.getenv("DEFAULT_CPU_TASK_MEMORY_MB", "256")
            ),
            heavy_cpu_task_memory_mb=int(
                os.getenv("HEAVY_CPU_TASK_MEMORY_MB", "2048")
            ),
            llm_task_memory_mb=int(os.getenv("LLM_TASK_MEMORY_MB", "512")),
            resource_check_interval=float(
                os.getenv("COMPUTING_RESOURCE_CHECK_INTERVAL", "0.5")
            ),
            ollama_timeout=float(os.getenv("OLLAMA_TIMEOUT", "300")),
            llm_retries=int(os.getenv("OLLAMA_RETRIES", "1")),
        )


COMPUTING_SETTINGS = ComputingSettings.from_env()
