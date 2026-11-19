import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import bot.runtime as runtime_module
from config.settings import SETTINGS


class FakeOllama:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.close_calls = 0
        self.__class__.instances.append(self)

    async def close(self):
        self.close_calls += 1


class FakeTrading212:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.session = Mock()


@pytest.fixture(autouse=True)
def reset_fake_clients():
    FakeOllama.instances = []


def patch_runtime_dependencies(monkeypatch):
    monkeypatch.setattr(runtime_module, "OllamaClient", FakeOllama)
    monkeypatch.setattr(runtime_module, "Trading212Client", FakeTrading212)

    monkeypatch.setattr(
        runtime_module,
        "MarketDataService",
        lambda trading212: SimpleNamespace(client=trading212),
    )
    monkeypatch.setattr(
        runtime_module,
        "create_risk_agent",
        lambda ollama: SimpleNamespace(name="risk", ollama=ollama),
    )
    monkeypatch.setattr(
        runtime_module,
        "create_technical_agent",
        lambda ollama: SimpleNamespace(name="technical", ollama=ollama),
    )
    monkeypatch.setattr(
        runtime_module,
        "create_portfolio_agent",
        lambda ollama: SimpleNamespace(name="portfolio", ollama=ollama),
    )
    monkeypatch.setattr(
        runtime_module,
        "AgentOrchestrator",
        lambda agents: SimpleNamespace(agents=agents),
    )
    monkeypatch.setattr(
        runtime_module,
        "DecisionAgent",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        runtime_module,
        "RiskManager",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        runtime_module,
        "OrderExecutor",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        runtime_module,
        "StopLossVerifier",
        lambda: SimpleNamespace(name="stop-loss-verifier"),
    )


def test_build_runtime_wires_dependencies_and_keeps_execution_safe(monkeypatch):
    patch_runtime_dependencies(monkeypatch)

    runtime = asyncio.run(
        runtime_module.build_runtime("test-credentials.json")
    )

    assert runtime.trading212.kwargs == {
        "credentials_path": "test-credentials.json",
        "demo_orders_enabled": False,
    }
    assert runtime.order_executor.dry_run is True
    assert runtime.decision_agent.min_confidence == 0.65
    assert len(runtime.orchestrator.agents) == 3
    assert runtime.market_data_service.client is runtime.trading212

    assert len(FakeOllama.instances) == 2
    assert all(
        client.kwargs["base_url"] == SETTINGS.ollama_base_url
        for client in FakeOllama.instances
    )

    asyncio.run(runtime.close())

    assert all(client.close_calls == 1 for client in FakeOllama.instances)
    runtime.trading212.session.close.assert_called_once()


def test_runtime_close_is_idempotent(monkeypatch):
    patch_runtime_dependencies(monkeypatch)

    runtime = asyncio.run(
        runtime_module.build_runtime("test-credentials.json")
    )

    asyncio.run(runtime.close())
    asyncio.run(runtime.close())

    assert all(client.close_calls == 1 for client in FakeOllama.instances)
    runtime.trading212.session.close.assert_called_once()


def test_build_runtime_closes_created_clients_if_initialization_fails(
    monkeypatch,
):
    patch_runtime_dependencies(monkeypatch)

    calls = 0

    def fail_second_ollama(**kwargs):
        nonlocal calls
        calls += 1

        if calls == 2:
            raise RuntimeError("Ollama initialization failed")

        return FakeOllama(**kwargs)

    monkeypatch.setattr(
        runtime_module,
        "OllamaClient",
        fail_second_ollama,
    )

    with pytest.raises(
        RuntimeError,
        match="Ollama initialization failed",
    ):
        asyncio.run(
            runtime_module.build_runtime("test-credentials.json")
        )

    assert len(FakeOllama.instances) == 1
    assert FakeOllama.instances[0].close_calls == 1
