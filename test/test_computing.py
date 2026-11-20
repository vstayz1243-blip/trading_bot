import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from computing.cpu_worker import CPUWorker
from computing.exceptions import ComputingShutdownError, TaskNotFoundError
from computing.llm_worker import LLMWorker
from computing.models import Task, TaskPriority, TaskStatus, TaskType
from computing.orchestrator import ComputingOrchestrator
from computing.resource_manager import ResourceManager
from config.computing import ComputingSettings


def multiply(value, factor):
    return value * factor


class FakeLLM:
    def __init__(self, response='{"action":"HOLD"}'):
        self.response = response
        self.calls = 0

    async def generate(self, prompt):
        self.calls += 1
        return self.response


class AlwaysAvailable:
    def can_start(self, *args):
        return True


class NeverAvailable:
    def can_start(self, *args):
        return False


def wait_for_status(orchestrator, task_id, status, timeout=3):
    async def _wait():
        async with asyncio.timeout(timeout):
            while orchestrator.get_task_status(task_id) is not status:
                await asyncio.sleep(0.01)
    asyncio.run(_wait())


def test_task_model_has_required_fields_and_serializes():
    task = Task(
        task_type=TaskType.BACKTEST,
        priority=TaskPriority.HIGH,
        metadata={"source": "unit-test"},
    )

    data = task.to_dict()

    assert data["task_id"] == str(task.task_id)
    assert data["task_type"] == "BACKTEST"
    assert data["priority"] == 8
    assert data["status"] == "PENDING"
    assert data["created_at"]
    assert data["started_at"] is None
    assert data["completed_at"] is None
    assert data["result"] is None
    assert data["error"] is None
    assert data["metadata"] == {"source": "unit-test"}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_cpu_workers": 0},
        {"max_llm_parallel": 0},
        {"max_total_tasks": 0},
        {"max_memory_usage_percent": 101},
        {"max_cpu_usage_percent": 0},
        {"max_cpu_workers": 5, "max_total_tasks": 4},
    ],
)
def test_computing_settings_reject_invalid_limits(kwargs):
    with pytest.raises(ValueError):
        ComputingSettings(**kwargs)


def test_resource_manager_enforces_memory_and_worker_limits(monkeypatch):
    settings = ComputingSettings(
        max_cpu_workers=1,
        max_llm_parallel=1,
        max_total_tasks=2,
    )
    manager = ResourceManager(settings)

    monkeypatch.setattr(
        "computing.resource_manager.psutil.virtual_memory",
        lambda: SimpleNamespace(
            percent=50.0,
            available=8_000_000_000,
            total=16_000_000_000,
        ),
    )
    monkeypatch.setattr(
        "computing.resource_manager.psutil.cpu_percent",
        lambda interval=None: 20.0,
    )
    monkeypatch.setattr(
        "computing.resource_manager.psutil.cpu_count",
        lambda logical=True: 8,
    )

    assert manager.can_start(TaskType.BACKTEST, 0, 0, 0)
    assert not manager.can_start(TaskType.BACKTEST, 1, 0, 1)
    assert manager.can_start(TaskType.AI_ANALYSIS, 0, 0, 0)
    assert not manager.can_start(TaskType.AI_ANALYSIS, 0, 1, 1)
    assert not manager.can_start(TaskType.AI_ANALYSIS, 0, 0, 2)

    monkeypatch.setattr(
        "computing.resource_manager.psutil.virtual_memory",
        lambda: SimpleNamespace(
            percent=85.0,
            available=2_400_000_000,
            total=16_000_000_000,
        ),
    )
    assert not manager.can_start(TaskType.AI_ANALYSIS, 0, 0, 0)


def test_cpu_worker_executes_in_process_pool():
    async def _run():
        worker = CPUWorker(
            ComputingSettings(max_cpu_workers=1, max_llm_parallel=1)
        )
        try:
            return await worker.run(multiply, (6, 7))
        finally:
            await worker.shutdown()

    assert asyncio.run(_run()) == 42


def test_llm_worker_returns_structured_json():
    async def _run():
        client = FakeLLM()
        worker = LLMWorker(
            client,
            ComputingSettings(max_cpu_workers=1, max_llm_parallel=2),
        )
        result = await worker.run({"prompt": "Analyse this portfolio"})
        return client, result

    client, result = asyncio.run(_run())
    assert client.calls == 1
    assert result["raw_response"] == '{"action":"HOLD"}'
    assert result["structured"] == {"action": "HOLD"}


def test_llm_worker_retries_transient_transport_failure():
    class FlakyLLM:
        def __init__(self):
            self.calls = 0

        async def generate(self, prompt):
            self.calls += 1
            if self.calls == 1:
                raise httpx.ConnectError("temporary connection failure")
            return '{"ok":true}'

    async def _run():
        client = FlakyLLM()
        worker = LLMWorker(
            client,
            ComputingSettings(
                max_cpu_workers=1,
                max_llm_parallel=1,
                llm_retries=1,
            ),
        )
        return client, await worker.run("prompt")

    client, result = asyncio.run(_run())
    assert client.calls == 2
    assert result["structured"] == {"ok": True}


def test_orchestrator_executes_registered_cpu_task_and_tracks_status():
    async def _run():
        settings = ComputingSettings(
            max_cpu_workers=1,
            max_llm_parallel=1,
            max_total_tasks=2,
            resource_check_interval=0.01,
        )
        orchestrator = ComputingOrchestrator(
            settings=settings,
            resource_manager=AlwaysAvailable(),
        )
        orchestrator.register_cpu_handler(TaskType.TECHNICAL_ANALYSIS, multiply)
        try:
            task = await orchestrator.submit_task(
                TaskType.TECHNICAL_ANALYSIS,
                payload=(7, 6),
                priority=TaskPriority.HIGH,
                metadata={"ticker": "AAPL_US_EQ"},
            )
            async with asyncio.timeout(3):
                while orchestrator.get_task_status(task.task_id) not in {
                    TaskStatus.COMPLETED,
                    TaskStatus.FAILED,
                }:
                    await asyncio.sleep(0.01)

            assert task.status is TaskStatus.COMPLETED
            assert task.result == 42
            assert task.started_at is not None
            assert task.completed_at is not None
            assert task.metadata["ticker"] == "AAPL_US_EQ"
        finally:
            await orchestrator.shutdown()

    asyncio.run(_run())


def test_orchestrator_marks_worker_errors_as_failed():
    async def _run():
        settings = ComputingSettings(
            max_cpu_workers=1,
            max_llm_parallel=1,
            max_total_tasks=2,
            resource_check_interval=0.01,
        )
        orchestrator = ComputingOrchestrator(
            settings=settings,
            resource_manager=AlwaysAvailable(),
        )
        try:
            task = await orchestrator.submit_task(TaskType.BACKTEST, payload={})
            async with asyncio.timeout(3):
                while task.status not in {TaskStatus.FAILED, TaskStatus.COMPLETED}:
                    await asyncio.sleep(0.01)
            assert task.status is TaskStatus.FAILED
            assert "No CPU handler registered" in task.error
        finally:
            await orchestrator.shutdown()

    asyncio.run(_run())


def test_pending_task_can_be_cancelled_and_unknown_task_raises():
    async def _run():
        settings = ComputingSettings(
            max_cpu_workers=1,
            max_llm_parallel=1,
            max_total_tasks=1,
            resource_check_interval=0.01,
        )
        orchestrator = ComputingOrchestrator(
            settings=settings,
            resource_manager=NeverAvailable(),
        )
        try:
            task = await orchestrator.submit_task(TaskType.BACKTEST)
            await asyncio.sleep(0.03)
            assert await orchestrator.cancel_task(task.task_id)
            assert task.status is TaskStatus.CANCELLED
            assert task.completed_at is not None
            with pytest.raises(TaskNotFoundError):
                orchestrator.get_task("00000000-0000-0000-0000-000000000000")
        finally:
            await orchestrator.shutdown()

    asyncio.run(_run())


def test_orchestrator_rejects_submissions_after_shutdown():
    async def _run():
        orchestrator = ComputingOrchestrator(
            settings=ComputingSettings(max_cpu_workers=1, max_llm_parallel=1)
        )
        await orchestrator.shutdown()
        with pytest.raises(ComputingShutdownError):
            await orchestrator.submit_task(TaskType.BACKTEST)

    asyncio.run(_run())
