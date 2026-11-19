
import asyncio
import logging
import math
import time
from dataclasses import replace
from typing import Any

from agents.ollama_client import OllamaClient
from agents.orchestrator import AgentOrchestrator
from agents.portfolio import create_portfolio_agent
from agents.risk import create_risk_agent
from agents.technical import create_technical_agent
from client import Trading212Client
from execution.order_executor import OrderExecutor
from services.market_data import MarketDataService
from services.order_sizing import OrderSizingService
from services.stop_loss_verifier import StopLossResult, StopLossVerifier
from strategy.decision import Action, DecisionAgent, TradingDecision
from strategy.risk_manager import RiskManager


logger = logging.getLogger(__name__)

MIN_CONFIDENCE = 0.65
MAX_ORDER_VALUE = 500.0
MAX_POSITION_VALUE = 1000.0
QUANTITY_PRECISION = 6

# Sicherheitskonfiguration:
# Es werden standardmäßig keine Orders an Trading 212 gesendet.
DRY_RUN = True

# Zusätzliche Freigabe für Demo-Orders.
# Bleibt deaktiviert, bis API-Antworten und Tests geprüft wurden.
DEMO_ORDERS_ENABLED = False


def _is_valid_number(value: Any) -> bool:
    """Prüft, ob ein Wert eine endliche Zahl und kein bool ist."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def print_analyses(analyses: Any) -> None:
    """Gibt die Analysen der Agenten aus."""
    print("\n" + "=" * 60)
    print("AGENT-ANALYSEN")
    print("=" * 60)

    if isinstance(analyses, dict):
        for agent_name, analysis in analyses.items():
            print(f"\n[{agent_name}]")
            print(analysis)
    elif isinstance(analyses, list):
        for index, analysis in enumerate(analyses, start=1):
            print(f"\n[Analyse {index}]")
            print(analysis)
    else:
        print(analyses)

    print("=" * 60)


def print_decision(decision: TradingDecision) -> None:
    """Gibt eine Trading-Entscheidung aus."""
    print("\n" + "-" * 60)
    print("TRADING-ENTSCHEIDUNG")
    print("-" * 60)
    print(f"Ticker:       {decision.ticker}")
    print(f"Aktion:       {decision.action}")
    print(f"Confidence:   {decision.confidence:.2f}")
    print(f"Kurs:         {decision.current_price}")
    print(f"Menge:        {decision.quantity}")
    print(f"Begründung:   {decision.reason}")
    print("-" * 60)


class TradingBot:
    def __init__(
        self,
        credentials_path: str = "credentials.json",
        interval: int = 300,
        ticker: str = "AAPL_US_EQ",
    ) -> None:
        if (
            isinstance(interval, bool)
            or not isinstance(interval, int)
            or interval <= 0
        ):
            raise ValueError(
                "Das Intervall muss eine positive Ganzzahl sein."
            )

        if not isinstance(ticker, str) or not ticker.strip():
            raise ValueError("Der Ticker darf nicht leer sein.")

        self.credentials_path = credentials_path
        self.interval = interval
        self.ticker = ticker.strip()
        self.order_sizing_service = OrderSizingService(
            max_order_value=MAX_ORDER_VALUE,
            quantity_precision=QUANTITY_PRECISION,
        )

    async def _run_once(
        self,
        market_data_service: MarketDataService,
        orchestrator: AgentOrchestrator,
        decision_agent: DecisionAgent,
        risk_manager: RiskManager,
        order_executor: OrderExecutor,
        trading212: Trading212Client,
        risk_agent: Any,
        stop_loss_verifier: StopLossVerifier,
    ) -> None:
        logger.info("Lade Marktdaten für %s.", self.ticker)

        market_data = await asyncio.to_thread(
            market_data_service.get_market_data,
            self.ticker,
        )

        if market_data.ticker != self.ticker:
            raise RuntimeError(
                f"Ticker-Abweichung: erwartet {self.ticker}, "
                f"erhalten {market_data.ticker}."
            )

        if (
            not _is_valid_number(market_data.current_price)
            or market_data.current_price <= 0
        ):
            raise RuntimeError(
                "Marktdaten enthalten keinen gültigen Kurs."
            )

        logger.info(
            "Marktdaten: %s | Kurs %.4f %s | Kontowährung %s | FX %s",
            market_data.ticker,
            market_data.current_price,
            market_data.currency,
            market_data.account_currency,
            market_data.fx_rate_to_account,
        )

        # Ohne erfolgreiche Verifikation bleibt der Stop-Loss unbekannt.
        stop_result = StopLossResult(
            status="UNKNOWN",
            approved=False,
            reason="Stop-Loss-Daten konnten nicht verifiziert werden.",
        )

        try:
            get_pending_orders = getattr(
                trading212,
                "get_pending_orders",
                None,
            )

            if not callable(get_pending_orders):
                stop_result = StopLossResult(
                    status="UNKNOWN",
                    approved=False,
                    reason=(
                        "Trading212Client stellt keine Methode "
                        "get_pending_orders() bereit."
                    ),
                )
            else:
                orders = await asyncio.to_thread(get_pending_orders)

                if not isinstance(orders, (list, tuple)):
                    raise ValueError(
                        "Trading 212 hat keine gültige Orderliste geliefert."
                    )

                positions = getattr(market_data, "positions", None)

                if not isinstance(positions, list):
                    raise ValueError(
                        "Marktdaten enthalten keine gültige Positionsliste."
                    )

                matching_positions = [
                    position
                    for position in positions
                    if getattr(position, "ticker", None) == self.ticker
                    and _is_valid_number(
                        getattr(position, "quantity", None)
                    )
                    and abs(position.quantity) > 0
                ]

                if len(matching_positions) != 1:
                    stop_result = StopLossResult(
                        status="UNKNOWN",
                        approved=False,
                        reason=(
                            "Es wurde nicht genau eine passende "
                            "bestehende Position gefunden."
                        ),
                    )
                else:
                    position = matching_positions[0]

                    stop_result = stop_loss_verifier.verify(
                        ticker=self.ticker,
                        position_quantity=abs(position.quantity),
                        current_price=market_data.current_price,
                        orders=list(orders),
                    )

        except Exception:
            logger.exception("Stop-Loss-Prüfung fehlgeschlagen.")

            stop_result = StopLossResult(
                status="UNKNOWN",
                approved=False,
                reason=(
                    "Fehler beim Abrufen oder Prüfen der Stop-Orders."
                ),
            )

        stop_loss_verified = (
            stop_result.status == "VERIFIED"
            and stop_result.approved is True
        )

        if not stop_loss_verified and stop_result.approved:
            stop_result = replace(stop_result, approved=False)

        risk_agent.stop_loss_result = stop_result

        logger.info(
            "Stop-Loss-Status: %s | Freigegeben: %s | %s",
            stop_result.status,
            stop_result.approved,
            stop_result.reason,
        )

        analysis_started = time.perf_counter()

        try:
            analyses = await orchestrator.analyze(market_data)
        finally:
            logger.info(
                "Agenten-Analyse abgeschlossen | Dauer: %.2f Sekunden",
                time.perf_counter() - analysis_started,
            )

        print_analyses(analyses)

        decision = decision_agent.decide(
            market_data=market_data,
            analyses=analyses,
        )

        print_decision(decision)

        if decision.action == Action.HOLD:
            logger.info(
                "HOLD: keine Order erforderlich. Grund: %s",
                decision.reason,
            )
            return

        # KORREKTUR:
        # Ein Erstkauf braucht keinen bereits existierenden Stop-Loss.
        # Bei einer bestehenden Position wird ein weiterer Kauf dagegen
        # blockiert, wenn der Schutz nicht eindeutig verifiziert ist.
        if decision.action == Action.BUY:
            positions = getattr(market_data, "positions", None)

            if not isinstance(positions, list):
                logger.error(
                    "BUY BLOCKIERT: Positionsdaten sind ungültig."
                )
                return

            matching_positions = [
                position
                for position in positions
                if getattr(position, "ticker", None) == decision.ticker
            ]

            if len(matching_positions) > 1:
                logger.error(
                    "BUY BLOCKIERT: Mehrere Positionen für %s gefunden.",
                    decision.ticker,
                )
                return

            existing_position = (
                matching_positions[0] if matching_positions else None
            )

            existing_quantity = (
                getattr(existing_position, "quantity", None)
                if existing_position is not None
                else 0.0
            )

            if not _is_valid_number(existing_quantity):
                logger.error(
                    "BUY BLOCKIERT: Menge der bestehenden Position ungültig."
                )
                return

            if abs(existing_quantity) > 0 and not stop_loss_verified:
                logger.error(
                    "BUY BLOCKIERT: Bestehende Position ist nicht "
                    "nachweislich abgesichert. Status=%s | Grund=%s",
                    stop_result.status,
                    stop_result.reason,
                )
                return

        sized_decision, validation_message = self.order_sizing_service.prepare_order(
            decision=decision,
            market_data=market_data,
            risk_manager=risk_manager,
        )

        logger.info("Risikoprüfung: %s", validation_message)

        if sized_decision is None:
            logger.warning("Keine Order wird vorbereitet.")
            return

        print_decision(sized_decision)

        # Die aktuelle Version erlaubt ausschließlich Dry-Run.
        if DRY_RUN is not True:
            raise RuntimeError(
                "Sicherheitsabbruch: Orderausführung ist in dieser "
                "Version gesperrt."
            )

        if getattr(order_executor, "dry_run", None) is not True:
            raise RuntimeError(
                "Sicherheitsabbruch: OrderExecutor ist nicht im Dry-Run."
            )

        result = order_executor.execute(sized_decision)

        logger.info("Dry-Run abgeschlossen: %s", result)

    async def run(self) -> None:
        ollama_clients: list[OllamaClient] = []
        trading212 = None

        try:
            technical_ollama = OllamaClient(
                base_url="http://localhost:11434",
                model="qwen3:8b",
                timeout=300.0,
                max_concurrent=1,
            )
            ollama_clients.append(technical_ollama)

            portfolio_ollama = OllamaClient(
                base_url="http://localhost:11434",
                model="qwen3:8b",
                timeout=300.0,
                max_concurrent=1,
            )
            ollama_clients.append(portfolio_ollama)

            trading212 = Trading212Client(
                credentials_path=self.credentials_path,
                demo_orders_enabled=DEMO_ORDERS_ENABLED,
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
                min_confidence=MIN_CONFIDENCE,
            )

            risk_manager = RiskManager(
                max_order_value=MAX_ORDER_VALUE,
                max_position_value=MAX_POSITION_VALUE,
            )

            order_executor = OrderExecutor(
                trading212=trading212,
                dry_run=True,
            )

            stop_loss_verifier = StopLossVerifier()

            logger.info(
                "TradingBot gestartet | Ticker=%s | Intervall=%ss | "
                "DRY_RUN=%s | DEMO_ORDERS_ENABLED=%s",
                self.ticker,
                self.interval,
                DRY_RUN,
                DEMO_ORDERS_ENABLED,
            )

            while True:
                try:
                    await self._run_once(
                        market_data_service=market_data_service,
                        orchestrator=orchestrator,
                        decision_agent=decision_agent,
                        risk_manager=risk_manager,
                        order_executor=order_executor,
                        trading212=trading212,
                        risk_agent=risk_agent,
                        stop_loss_verifier=stop_loss_verifier,
                    )

                except asyncio.CancelledError:
                    raise

                except Exception:
                    logger.exception(
                        "Trading-Durchlauf fehlgeschlagen. "
                        "Dieser Durchlauf wird nicht wiederholt."
                    )

                logger.info(
                    "Nächster Durchlauf in %s Sekunden.",
                    self.interval,
                )

                await asyncio.sleep(self.interval)

        except asyncio.CancelledError:
            logger.info("TradingBot wurde beendet.")
            raise

        finally:
            try:
                close_results = await asyncio.gather(
                    *(client.close() for client in ollama_clients),
                    return_exceptions=True,
                )

                for result in close_results:
                    if isinstance(result, BaseException):
                        logger.error(
                            "Ollama-Client konnte nicht sauber "
                            "geschlossen werden: %s: %s",
                            type(result).__name__,
                            result,
                        )

            finally:
                if trading212 is not None:
                    session = getattr(trading212, "session", None)

                    if session is not None:
                        try:
                            await asyncio.to_thread(session.close)
                        except Exception:
                            logger.exception(
                                "Trading212-Session konnte nicht "
                                "sauber geschlossen werden."
                            )

                logger.info("TradingBot-Ressourcen geschlossen.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    try:
        asyncio.run(TradingBot().run())
    except KeyboardInterrupt:
        print("\nTradingBot manuell beendet.")
