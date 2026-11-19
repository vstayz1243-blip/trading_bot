
import asyncio
import logging
import time

from agents.ollama_client import OllamaClient
from agents.technical import create_technical_agent
from agents.portfolio import create_portfolio_agent
from models.market_data import MarketData, Position


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


def create_sample_market_data() -> MarketData:
    """Erstellt Beispieldaten ohne API-Zugriff oder Orderausführung."""

    return MarketData(
        ticker="AAPL_US_EQ",
        current_price=341.91,
        currency="USD",
        fx_rate_to_account=0.8892,
        change_24h=None,
        volume=None,
        positions=[
            Position(
                ticker="AAPL_US_EQ",
                quantity=0.18,
                average_price=335.80,
                current_price=341.91,
                profit_loss=1.10,
                profit_loss_percentage=1.82,
                currency="USD",
            )
        ],
        account_cash=4940.92,
        account_equity=5001.76,
        account_currency="EUR",
        historical_data_points=50,
        technical_indicators={
            "ema20": 339.50,
            "sma20": 338.90,
            "sma50": 345.20,
            "rsi14": 60.48,
            "atr14": 6.64,
        },
        portfolio_metrics={
            "largest_position_weight_percent": 1.22,
            "all_position_weights_calculable": True,
            "unknown_currency_positions": 0,
        },
    )


async def measure_agent(agent, market_data):
    """Misst einen einzelnen Agenten und erfasst Fehler."""

    started_at = time.perf_counter()

    try:
        result = await agent.analyze(market_data)
        error = None
    except Exception as exc:
        result = None
        error = f"{type(exc).__name__}: {exc}"

    duration = time.perf_counter() - started_at

    return {
        "name": agent.name,
        "duration": duration,
        "result": result,
        "error": error,
    }


async def run_sequential(market_data):
    """Beide Agenten nacheinander mit einem gemeinsamen Client."""

    client = OllamaClient(max_concurrent=1)

    try:
        agents = [
            create_technical_agent(client),
            create_portfolio_agent(client),
        ]

        started_at = time.perf_counter()
        results = []

        for agent in agents:
            results.append(
                await measure_agent(agent, market_data)
            )

        total_duration = time.perf_counter() - started_at

        return total_duration, results

    finally:
        await client.close()


async def run_parallel(market_data):
    """Beide Agenten gleichzeitig über getrennte Clients."""

    technical_client = OllamaClient(max_concurrent=1)
    portfolio_client = OllamaClient(max_concurrent=1)

    try:
        agents = [
            create_technical_agent(technical_client),
            create_portfolio_agent(portfolio_client),
        ]

        started_at = time.perf_counter()

        results = await asyncio.gather(
            *(
                measure_agent(agent, market_data)
                for agent in agents
            )
        )

        total_duration = time.perf_counter() - started_at

        return total_duration, results

    finally:
        await asyncio.gather(
            technical_client.close(),
            portfolio_client.close(),
        )


def print_results(title, total_duration, results):
    print(f"\n{'=' * 65}")
    print(title)
    print(f"{'=' * 65}")

    for item in results:
        print(
            f"\n{item['name']}: "
            f"{item['duration']:.2f} Sekunden"
        )

        if item["error"]:
            print(f"FEHLER: {item['error']}")
        else:
            print("Antwort:")
            print(item["result"])

    print(f"\nGesamtdauer: {total_duration:.2f} Sekunden")


async def main():
    market_data = create_sample_market_data()

    print("Benchmark gestartet.")
    print("Modell: qwen3:8b")
    print("Orderausführung: deaktiviert")
    print("Hinweis: Es werden vier LLM-Anfragen ausgeführt.")

    sequential_time, sequential_results = await run_sequential(
        market_data
    )

    print_results(
        "TEST 1: SEQUENZIELL",
        sequential_time,
        sequential_results,
    )

    parallel_time, parallel_results = await run_parallel(
        market_data
    )

    print_results(
        "TEST 2: PARALLEL",
        parallel_time,
        parallel_results,
    )

    print(f"\n{'=' * 65}")
    print("ERGEBNIS")
    print(f"{'=' * 65}")

    if sequential_time > 0:
        saved_seconds = sequential_time - parallel_time
        improvement = (
            saved_seconds / sequential_time
        ) * 100

        print(f"Sequenziell: {sequential_time:.2f} Sekunden")
        print(f"Parallel:    {parallel_time:.2f} Sekunden")
        print(f"Zeitdifferenz: {saved_seconds:.2f} Sekunden")
        print(f"Zeitersparnis: {improvement:.1f} %")

        if saved_seconds > 0:
            print("Ergebnis: Parallel war schneller.")
        elif saved_seconds < 0:
            print("Ergebnis: Sequenziell war schneller.")
        else:
            print("Ergebnis: Beide Varianten waren gleich schnell.")

    if any(
        item["error"]
        for item in sequential_results + parallel_results
    ):
        print(
            "\nWARNUNG: Mindestens eine Analyse ist "
            "fehlgeschlagen. Vergleiche die Laufzeiten "
            "nur eingeschränkt."
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBenchmark manuell beendet.")
