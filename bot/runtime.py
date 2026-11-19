import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from agents.ollama_client import OllamaClient
from agents.orchestrator import AgentOrchestrator
from agents.portfolio import create_portfolio_agent
from agents.risk import create_risk_agent
from agents.technical import create_technical_agent
from client import Trading212Client
from config.risk_limits import RISK_LIMITS
from config.settings import SETTINGS
from execution.order_executor import OrderExecutor
from services.market_data import MarketDataService
from services.stop_loss_verifier import StopLossVerifier
from strategy.decision import DecisionAgent
from strategy.risk_manager import RiskManager


logger = logging.getLogger(__name__)


async def _close_resources(
    ollama_clients: list[OllamaClient],
    trading212: Trading212Client | None,
) -> None:
    """Close all resources, attempting every close even after failures."""
    close_operations = [
        client.close()
        for client in ollama_clients
    ]

    if trading212 is not None:
        session = getattr(trading212, "session", None)
        if session is not None:
            close_operations.append(asyncio.to_thread(session.close))

    if not close_operations:
        return

    results = await asyncio.gather(
        *close_operations,
        return_exceptions=True,
    )

    for result in results:
        if isinstance(result, BaseException):
            logger.error(
                "Ressource konnte nicht sauber geschlossen werden: %s: %s",
                type(result).__name__,
                result,
            )


@dataclass(slots=True)
class BotRuntime:
    """Holds the fully initialized dependencies of one bot instance."""

    technical_ollama: OllamaClient
    portfolio_ollama: OllamaClient
    trading212: Trading212Client
    market_data_service: MarketDataService
    orchestrator: AgentOrchestrator
    decision_agent: DecisionAgent
    risk_manager: RiskManager
    order_executor: OrderExecutor
    risk_agent: Any
    stop_loss_verifier: StopLossVerifier

    _closed: bool = field(default=False, init=False, repr=False)

    async def close(self) -> None:
        """Idempotently release all external resources."""
        if self._closed:
            return

        self._closed = True
        await _close_resources(
            ollama_clients=[
                self.technical_ollama,
                self.portfolio_ollama,
            ],
            trading212=self.trading212,
        )
        logger.info("TradingBot-Ressourcen geschlossen.")


async def build_runtime(
    credentials_path: str,
) -> BotRuntime:
    """Construct all bot dependencies and clean up partial setup on failure."""
    ollama_clients: list[OllamaClient] = []
    trading212: Trading212Client | None = None

    try:
        technical_ollama = OllamaClient(
            base_url=SETTINGS.ollama_base_url,
            model=SETTINGS.ollama_model,
            timeout=SETTINGS.ollama_timeout,
            max_concurrent=SETTINGS.ollama_max_concurrent,
        )
        ollama_clients.append(technical_ollama)

        portfolio_ollama = OllamaClient(
            base_url=SETTINGS.ollama_base_url,
            model=SETTINGS.ollama_model,
            timeout=SETTINGS.ollama_timeout,
            max_concurrent=SETTINGS.ollama_max_concurrent,
        )
        ollama_clients.append(portfolio_ollama)

        trading212 = Trading212Client(
            credentials_path=credentials_path,
            demo_orders_enabled=SETTINGS.demo_orders_enabled,
        )

        market_data_service = MarketDataService(trading212)
        risk_agent = create_risk_agent(technical_ollama)

        agents = [
            create_technical_agent(technical_ollama),
            risk_agent,
            create_portfolio_agent(portfolio_ollama),
        ]
        orchestrator = AgentOrchestrator(agents)

        decision_agent = DecisionAgent(
            min_confidence=RISK_LIMITS.min_confidence,
        )
        risk_manager = RiskManager(
            max_order_value=RISK_LIMITS.max_order_value,
            max_position_value=RISK_LIMITS.max_position_value,
        )
        order_executor = OrderExecutor(
            trading212=trading212,
            dry_run=SETTINGS.dry_run,
        )

        return BotRuntime(
            technical_ollama=technical_ollama,
            portfolio_ollama=portfolio_ollama,
            trading212=trading212,
            market_data_service=market_data_service,
            orchestrator=orchestrator,
            decision_agent=decision_agent,
            risk_manager=risk_manager,
            order_executor=order_executor,
            risk_agent=risk_agent,
            stop_loss_verifier=StopLossVerifier(),
        )

    except BaseException:
        await _close_resources(
            ollama_clients=ollama_clients,
            trading212=trading212,
        )
        raise
