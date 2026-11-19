
import json
from typing import Any

from agents.ollama_client import OllamaClient
from models.market_data import MarketData
from services.stop_loss_verifier import StopLossResult


class TradingAgent:
    def __init__(
        self,
        name: str,
        role: str,
        ollama: OllamaClient,
    ) -> None:
        self.name = name
        self.role = role
        self.ollama = ollama
        self.stop_loss_result: StopLossResult | None = None

    async def analyze(self, market_data: MarketData) -> str:
        positions = [
            {
                "ticker": position.ticker,
                "quantity": position.quantity,
                "average_price": position.average_price,
                "current_price": position.current_price,
                "profit_loss": position.profit_loss,
                "profit_loss_percentage": (
                    position.profit_loss_percentage
                ),
                "currency": position.currency,
            }
            for position in market_data.positions
        ]

        data = {
            "ticker": market_data.ticker,
            "current_price": market_data.current_price,
            "currency": market_data.currency,
            "fx_rate_to_account": market_data.fx_rate_to_account,
            "change_24h_percent": market_data.change_24h,
            "volume": market_data.volume,
            "account_cash": market_data.account_cash,
            "account_equity": market_data.account_equity,
            "account_currency": market_data.account_currency,
            "historical_data_points": market_data.historical_data_points,
            "technical_indicators": market_data.technical_indicators,
            "portfolio_metrics": market_data.portfolio_metrics,
            "positions": positions,
        }

        if self.name.strip().casefold() == "risk analyst":
            return self._analyze_risk_deterministically(data)

        prompt = f"""
Du bist der Trading-Agent: {self.name}

DEINE ROLLE:
{self.role}

MARKTDATEN:
{json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)}

REGELN:
- Verwende ausschließlich die übergebenen Daten.
- Erfinde keine Werte oder fehlenden Kennzahlen.
- null bedeutet, dass ein Wert nicht verfügbar ist.
- Behaupte nicht, Orders geprüft oder ausgeführt zu haben.
- Gib ausschließlich ein gültiges JSON-Objekt zurück.
- Keine Markdown-Codeblöcke und kein zusätzlicher Text.

JSON-Felder:
{{
  "action": "BUY | SELL | HOLD",
  "confidence": 0.0,
  "reason": "Begründung auf Basis der vorhandenen Daten"
}}

confidence muss zwischen 0.0 und 1.0 liegen.
Die Confidence ist keine statistisch kalibrierte Wahrscheinlichkeit.
Die verbindliche Risikoprüfung erfolgt durch Python.
"""

        return await self.ollama.generate(prompt)

    def _analyze_risk_deterministically(
        self,
        data: dict[str, Any],
    ) -> str:
        metrics = data.get("portfolio_metrics")
        if not isinstance(metrics, dict):
            metrics = {}

        reasons: list[str] = []
        stop_result = self.stop_loss_result

        approved = (
            stop_result is not None
            and stop_result.status == "VERIFIED"
            and stop_result.approved is True
        )

        if stop_result is None or stop_result.status == "UNKNOWN":
            reasons.append(
                "Stop-Loss-Status anhand der verfügbaren Daten "
                "nicht überprüfbar."
            )
        else:
            reasons.append(stop_result.reason)

        largest_weight = metrics.get(
            "largest_position_weight_percent"
        )

        if (
            isinstance(largest_weight, (int, float))
            and not isinstance(largest_weight, bool)
        ):
            reasons.append(
                f"Größte Positionsgewichtung: {largest_weight:.2f} %."
            )
        else:
            reasons.append(
                "Größte Positionsgewichtung nicht verfügbar."
            )

        unknown_currencies = metrics.get(
            "unknown_currency_positions"
        )

        if (
            isinstance(unknown_currencies, int)
            and not isinstance(unknown_currencies, bool)
            and unknown_currencies > 0
        ):
            reasons.append(
                f"Währung bei {unknown_currencies} Position(en) unbekannt."
            )

        if metrics.get("all_position_weights_calculable") is not True:
            reasons.append(
                "Nicht alle Positionsgewichtungen sind zuverlässig "
                "berechenbar."
            )

        result = {
            "action": "HOLD",
            "approved": approved,
            "confidence": 1.0,
            "reason": " ".join(reasons),
        }

        return json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
