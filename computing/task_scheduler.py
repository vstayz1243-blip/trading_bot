import asyncio
import itertools
import logging
from typing import Any
from uuid import UUID

from config.computing import COMPUTING_SETTINGS, ComputingSettings
from computing.exceptions import ComputingShutdownError, TaskNotFoundError
from computing.models import (
    TERMINAL_STATUSES,
    Task,
    TaskPriority,
    TaskStatus,
    TaskType,
    utc_now,
)
from computing.resource_manager import ResourceManager
from computing.worker_manager import WorkerManager


logger = logging.getLogger(__name__)


class TaskScheduler:
    """Priority queue with per-worker and host-resource admission control."""

    def __init__(
        self,
        worker_manager: WorkerManager,
        resource_manager: ResourceManager,
        settings: ComputingSettings = COMPUTING_SETTINGS,
    ):
        self.worker_manager = worker_manager
        self.resource_manager = resource_manager
        self.settings = settings
        self._queue: asyncio.PriorityQueue[tuple[int, int, str]] = (
            asyncio.PriorityQueue()
        )
        self._sequence = itertools.count()
        self._tasks: dict[str, Task] = {}
        self._active: dict[str, asyncio.Task[None]] = {}
        self._dispatcher: asyncio.Task[None] | None = None
        self._changed = asyncio.Event()
        self._closing = False

    def start(self) -> None:
        if self._closing:
            raise ComputingShutdownError("Scheduler is shutting down.")
        if self._dispatcher is None or self._dispatcher.done():
            self._dispatcher = asyncio.create_task(
                self._dispatch_loop(),
                name="computing-task-scheduler",
            )

    async def submit(
        self,
        task_type: TaskType,
        payload: Any = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        if self._closing:
            raise ComputingShutdownError("Scheduler is shutting down.")
        task = Task(
            task_type=task_type,
            priority=priority,
            payload=payload,
            metadata=metadata or {},
            status=TaskStatus.QUEUED,
        )
        key = str(task.task_id)
        self._tasks[key] = task
        await self._queue.put((-int(task.priority), next(self._sequence), key))
        self.start()
        self._changed.set()
        return task

    async def _dispatch_loop(self) -> None:
        while not self._closing:
            try:
                _, _, task_id = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=self.settings.resource_check_interval,
                )
            except asyncio.TimeoutError:
                continue

            task = self._tasks.get(task_id)
            if task is None or task.status is TaskStatus.CANCELLED:
                continue

            active_cpu = sum(
                1 for item in self._active
                if self._tasks[item].task_type in self.worker_manager.CPU_TASK_TYPES
            )
            active_llm = len(self._active) - active_cpu
            active_total = len(self._active)

            try:
                can_start = await asyncio.to_thread(
                    self.resource_manager.can_start,
                    task.task_type,
                    active_cpu,
                    active_llm,
                    active_total,
                )
            except Exception:
                logger.exception("Resource check failed; task remains queued.")
                can_start = False

            if not can_start:
                await self._queue.put(
                    (-int(task.priority), next(self._sequence), task_id)
                )
                try:
                    await asyncio.wait_for(
                        self._changed.wait(),
                        timeout=self.settings.resource_check_interval,
                    )
                except asyncio.TimeoutError:
                    pass
                self._changed.clear()
                continue

            execution = asyncio.create_task(
                self._execute(task),
                name=f"computing-{task.task_id}",
            )
            self._active[task_id] = execution
            self._changed.set()

    async def _execute(self, task: Task) -> None:
        task.status = TaskStatus.RUNNING
        task.started_at = task.started_at or utc_now()
        self._changed.set()

        try:
            task.result = await self.worker_manager.execute(task)
            task.status = TaskStatus.COMPLETED
        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
            raise
        except Exception as exc:
            task.error = f"{type(exc).__name__}: {exc}"
            task.status = TaskStatus.FAILED
            logger.exception("Task %s failed.", task.task_id)
        finally:
            task.completed_at = utc_now()
            self._active.pop(str(task.task_id), None)
            self._changed.set()

    def get_task(self, task_id: UUID | str) -> Task:
        key = str(task_id)
        task = self._tasks.get(key)
        if task is None:
            raise TaskNotFoundError(f"Task {key} was not found.")
        return task

    def get_task_status(self, task_id: UUID | str) -> TaskStatus:
        return self.get_task(task_id).status

    async def cancel_task(self, task_id: UUID | str) -> bool:
        task = self.get_task(task_id)
        if task.status in TERMINAL_STATUSES:
            return False

        key = str(task.task_id)
        active = self._active.get(key)
        if active is not None:
            active.cancel()
            return True

        task.status = TaskStatus.CANCELLED
        task.completed_at = utc_now()
        self._changed.set()
        return True

    def get_active_tasks(self) -> list[Task]:
        return [
            self._tasks[key]
            for key in self._active
            if self._tasks[key].status is TaskStatus.RUNNING
        ]

    def get_queued_tasks(self) -> list[Task]:
        return [
            task for task in self._tasks.values()
            if task.status is TaskStatus.QUEUED
        ]

    async def shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True

        for task in self._tasks.values():
            if task.status is TaskStatus.QUEUED:
                task.status = TaskStatus.CANCELLED
                task.completed_at = utc_now()

        if self._dispatcher is not None:
            self._dispatcher.cancel()
            await asyncio.gather(self._dispatcher, return_exceptions=True)

        for execution in self._active.values():
            execution.cancel()
        if self._active:
            await asyncio.gather(*self._active.values(), return_exceptions=True)

        await self.worker_manager.shutdown()
