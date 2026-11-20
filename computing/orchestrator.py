from typing import Any
from uuid import UUID

from config.computing import COMPUTING_SETTINGS, ComputingSettings
from computing.cpu_worker import CPUWorker
from computing.llm_worker import AsyncLLMClient, LLMWorker
from computing.models import Task, TaskPriority, TaskStatus, TaskType
from computing.resource_manager import ResourceManager
from computing.task_scheduler import TaskScheduler
from computing.worker_manager import WorkerManager


class ComputingOrchestrator:
    """Public facade for submitting and managing local compute tasks."""

    def __init__(
        self,
        llm_client: AsyncLLMClient | None = None,
        settings: ComputingSettings = COMPUTING_SETTINGS,
        resource_manager: ResourceManager | None = None,
    ):
        self.settings = settings
        cpu_worker = CPUWorker(settings)
        llm_worker = (
            LLMWorker(llm_client, settings) if llm_client is not None else None
        )
        self.worker_manager = WorkerManager(cpu_worker, llm_worker)
        self.resource_manager = resource_manager or ResourceManager(settings)
        self.scheduler = TaskScheduler(
            self.worker_manager,
            self.resource_manager,
            settings,
        )

    def register_cpu_handler(
        self,
        task_type: TaskType,
        handler: Any,
    ) -> None:
        self.worker_manager.register_cpu_handler(task_type, handler)

    async def submit_task(
        self,
        task_type: TaskType,
        payload: Any = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        return await self.scheduler.submit(
            task_type=task_type,
            payload=payload,
            priority=priority,
            metadata=metadata,
        )

    def get_task(self, task_id: UUID | str) -> Task:
        return self.scheduler.get_task(task_id)

    def get_task_status(self, task_id: UUID | str) -> TaskStatus:
        return self.scheduler.get_task_status(task_id)

    async def cancel_task(self, task_id: UUID | str) -> bool:
        return await self.scheduler.cancel_task(task_id)

    def get_active_tasks(self) -> list[Task]:
        return self.scheduler.get_active_tasks()

    def get_system_resources(self) -> dict[str, Any]:
        active = self.scheduler.get_active_tasks()
        cpu_count = sum(
            1 for task in active
            if task.task_type in self.worker_manager.CPU_TASK_TYPES
        )
        llm_count = len(active) - cpu_count
        return self.resource_manager.get_snapshot(
            active_cpu_workers=cpu_count,
            active_llm_requests=llm_count,
            active_tasks=len(active),
        ).to_dict()

    async def shutdown(self) -> None:
        await self.scheduler.shutdown()
