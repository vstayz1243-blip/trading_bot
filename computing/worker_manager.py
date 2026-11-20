from collections.abc import Callable
from typing import Any

from computing.cpu_worker import CPUWorker
from computing.exceptions import TaskExecutionError
from computing.llm_worker import LLMWorker
from computing.models import Task, TaskType


class WorkerManager:
    """Routes tasks to CPU processes or the injected local LLM client."""

    CPU_TASK_TYPES = {
        TaskType.BACKTEST,
        TaskType.STRATEGY_OPTIMIZATION,
        TaskType.TECHNICAL_ANALYSIS,
        TaskType.PORTFOLIO_ANALYSIS,
    }

    def __init__(
        self,
        cpu_worker: CPUWorker,
        llm_worker: LLMWorker | None = None,
    ):
        self.cpu_worker = cpu_worker
        self.llm_worker = llm_worker
        self._cpu_handlers: dict[TaskType, Callable[..., Any]] = {}

    def register_cpu_handler(
        self,
        task_type: TaskType,
        handler: Callable[..., Any],
    ) -> None:
        if task_type not in self.CPU_TASK_TYPES:
            raise ValueError(f"{task_type.value} is not a CPU task type.")
        if not callable(handler):
            raise TypeError("handler must be callable.")
        self._cpu_handlers[task_type] = handler

    def worker_type(self, task_type: TaskType) -> str:
        return "llm" if task_type is TaskType.AI_ANALYSIS else "cpu"

    async def execute(self, task: Task) -> Any:
        if task.task_type is TaskType.AI_ANALYSIS:
            if self.llm_worker is None:
                raise TaskExecutionError(
                    "No Ollama client was supplied to the ComputingOrchestrator."
                )
            return await self.llm_worker.run(task.payload)

        handler = self._cpu_handlers.get(task.task_type)
        if handler is None:
            raise TaskExecutionError(
                f"No CPU handler registered for {task.task_type.value}."
            )
        return await self.cpu_worker.run(handler, task.payload)

    async def shutdown(self) -> None:
        # The Ollama client lifecycle belongs to the component that injected it.
        await self.cpu_worker.shutdown()
