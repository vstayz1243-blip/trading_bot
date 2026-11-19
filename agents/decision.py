
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any


class Action(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass(frozen=True)
class TradingDecision:
    ticker: str
    action: Action
    confidence: float
    reason: str
    current_price: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence muss zwischen 0.0 und 1.0 liegen")

        if self.current_price < 0:
            raise ValueError("current_price darf nicht negativ sein")

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "action": self.action.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "current_price": self.current_price,
        }


class DecisionAgent:
    """
    Wertet die JSON-Analysen der Ollama-Agenten aus.

    Erwartete Schlüssel:
        Technical Analyst
        Risk Analyst
        Portfolio Analyst

    Dieser Agent führt keine Orders aus.
    """

    def __init__(
        self,
        min_confidence: float = 0.65,
    ) -> None:
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError(
                "min_confidence muss zwischen 0.0 und 1.0 liegen"
            )

        self.min_confidence = min_confidence

    @staticmethod
    def _get_value(
        data: Any,
        key: str,
        default: Any = None,
    ) -> Any:
        if isinstance(data, dict):
            return data.get(key, default)

        return getattr(data, key, default)

    @staticmethod
    def _parse_analysis(raw: Any) -> dict[str, Any] | None:
        """
        Akzeptiert JSON-Strings oder bereits geparste Dictionaries.
        Ungültige oder unvollständige Antworten werden abgelehnt.
        """
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return None

        if not isinstance(raw, dict):
            return None

        action = raw.get("action")
        confidence = raw.get("confidence")
        reason = raw.get("reason")

        if not isinstance(action, str):
            return None

        try:
            action = Action(action.strip().upper())
        except ValueError:
            return None

        # bool ist in Python eine Unterklasse von int.
        if isinstance(confidence, bool):
            return None

        if not isinstance(confidence, (int, float)):
            return None

        confidence = float(confidence)

        if not 0.0 <= confidence <= 1.0:
            return None

        if not isinstance(reason, str) or not reason.strip():
            return None

        return {
            "action": action,
            "confidence": confidence,
            "reason": reason.strip(),
        }

    def decide(
        self,
        market_data: Any,
        analyses: dict[str, Any],
    ) -> TradingDecision:
        ticker = str(
            self._get_value(market_data, "ticker", "")
        )

        try:
            current_price = float(
                self._get_value(market_data, "current_price", 0.0)
            )
        except (TypeError, ValueError):
            current_price = 0.0

        if not ticker:
            ticker = "UNKNOWN"

        if current_price <= 0:
            return TradingDecision(
                ticker=ticker,
                action=Action.HOLD,
                confidence=1.0,
                reason="Ungültiger oder fehlender Marktpreis.",
                current_price=max(current_price, 0.0),
            )

        if not isinstance(analyses, dict):
            analyses = {}

        # Die Namen entsprechen den Agenten aus agents/technical.py usw.
        aliases = {
            "technical": "Technical Analyst",
            "risk": "Risk Analyst",
            "portfolio": "Portfolio Analyst",
        }

        normalized: dict[str, Any] = {}

        for short_name, full_name in aliases.items():
            if full_name in analyses:
                normalized[short_name] = analyses[full_name]
            elif short_name in analyses:
                normalized[short_name] = analyses[short_name]
            else:
                return TradingDecision(
                    ticker=ticker,
                    action=Action.HOLD,
                    confidence=1.0,
                    reason=f"Analyse fehlt: {full_name}.",
                    current_price=current_price,
                )

        parsed = {
            name: self._parse_analysis(raw)
            for name, raw in normalized.items()
        }

        invalid = [
            name
            for name, result in parsed.items()
            if result is None
        ]

        if invalid:
            return TradingDecision(
                ticker=ticker,
                action=Action.HOLD,
                confidence=1.0,
                reason=(
                    "Ungültige oder nicht parsebare Analyse: "
                    + ", ".join(invalid)
                ),
                current_price=current_price,
            )

        technical = parsed["technical"]
        risk = parsed["risk"]
        portfolio = parsed["portfolio"]

        # Risikoeinwände blockieren den Handel.
        if risk["action"] in (Action.SELL, Action.HOLD):
            return TradingDecision(
                ticker=ticker,
                action=Action.HOLD,
                confidence=risk["confidence"],
                reason=(
                    "Keine Risikofreigabe. "
                    f"Risk Analyst: {risk['reason']}"
                ),
                current_price=current_price,
            )

        # Alle drei Agenten müssen in der Handelsrichtung übereinstimmen.
        if (
            technical["action"] != portfolio["action"]
            or technical["action"] == Action.HOLD
        ):
            return TradingDecision(
                ticker=ticker,
                action=Action.HOLD,
                confidence=min(
                    technical["confidence"],
                    portfolio["confidence"],
                ),
                reason=(
                    "Technical Analyst und Portfolio Analyst "
                    "liefern kein übereinstimmendes Handelssignal."
                ),
                current_price=current_price,
            )

        confidence = min(
            technical["confidence"],
            risk["confidence"],
            portfolio["confidence"],
        )

        if confidence < self.min_confidence:
            return TradingDecision(
                ticker=ticker,
                action=Action.HOLD,
                confidence=confidence,
                reason=(
                    f"Confidence {confidence:.0%} liegt unter dem "
                    f"Mindestwert von {self.min_confidence:.0%}."
                ),
                current_price=current_price,
            )

        action = technical["action"]

        return TradingDecision(
            ticker=ticker,
            action=action,
            confidence=confidence,
            reason=(
                f"Technical Analyst: {technical['reason']} | "
                f"Risk Analyst: {risk['reason']} | "
                f"Portfolio Analyst: {portfolio['reason']}"
            ),
            current_price=current_price,
        )
