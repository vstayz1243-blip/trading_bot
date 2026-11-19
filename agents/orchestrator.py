
import asyncio
import logging
import time

from agents.agent import TradingAgent
from models.market_data import MarketData


logger = logging.getLogger(__name__)


class AgentOrchestrator:
    def __init__(self, agents: list[TradingAgent]):
        self.agents = agents

    async def _analyze_agent(
        self,
        agent: TradingAgent,
        market_data: MarketData,
    ) -> tuple[str, str]:
        started_at = time.perf_counter()

        logger.info("[Agent] %s startet.", agent.name)

        try:
            result = await agent.analyze(market_data)

            duration = time.perf_counter() - started_at

            logger.info(
                "[Agent] %s fertig | Dauer: %.2f Sekunden",
                agent.name,
                duration,
            )

            return agent.name, result

        except Exception:
            duration = time.perf_counter() - started_at

            logger.exception(
                "[Agent] %s fehlgeschlagen | Dauer: %.2f Sekunden",
                agent.name,
                duration,
            )
            raise

    async def analyze(
        self,
        market_data: MarketData,
    ) -> dict[str, str]:
        started_at = time.perf_counter()

        try:
            results = await asyncio.gather(
                *(
                    self._analyze_agent(agent, market_data)
                    for agent in self.agents
                ),
                return_exceptions=True,
            )

            failures = [
                result
                for result in results
                if isinstance(result, BaseException)
            ]

            if failures:
                for failure in failures:
                    logger.error(
                        "[Orchestrator] Agentenanalyse fehlgeschlagen: "
                        "%s: %s",
                        type(failure).__name__,
                        failure,
                    )

                first_failure = failures[0]

                if isinstance(first_failure, asyncio.CancelledError):
                    raise first_failure

                raise RuntimeError(
                    f"{len(failures)} Agentenanalyse(n) fehlgeschlagen. "
                    "Es wird keine Handelsentscheidung getroffen."
                ) from first_failure

            return dict(results)

        finally:
            duration = time.perf_counter() - started_at

            logger.info(
                "[Orchestrator] Analyse abgeschlossen | "
                "Gesamtdauer: %.2f Sekunden",
                duration,
            )
