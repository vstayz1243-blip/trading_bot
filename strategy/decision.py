import json
from dataclasses import dataclass
from enum import Enum
from typing import Any
import math


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
    quantity: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.ticker, str) or not self.ticker.strip():
            raise ValueError("Ticker muss ein nicht leerer String sein.")

        if not isinstance(self.action, Action):
            raise ValueError("Ungültige Handelsaktion.")

        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("Die Begründung darf nicht leer sein.")

        for name, value in (
            ("confidence", self.confidence),
            ("current_price", self.current_price),
            ("quantity", self.quantity),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(
                    f"{name} muss eine endliche Zahl sein."
                )

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "Confidence muss zwischen 0 und 1 liegen."
            )

        if self.current_price < 0:
            raise ValueError(
                "Der aktuelle Preis darf nicht negativ sein."
            )

        if self.quantity < 0:
            raise ValueError(
                "Die Ordermenge darf nicht negativ sein."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "action": self.action.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "current_price": self.current_price,
            "quantity": self.quantity,
        }
    
class DecisionAgent:
    def __init__(self, min_confidence: float = 0.65) -> None:
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError(
                "min_confidence muss zwischen 0 und 1 liegen."
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
    def _parse_analysis(
        raw: Any,
        require_approval: bool = False,
    ) -> dict[str, Any]:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "Antwort ist kein gültiges JSON."
                ) from exc

        if not isinstance(raw, dict):
            raise ValueError("Analyse muss ein JSON-Objekt sein.")

        try:
            action = Action(raw["action"])
            confidence = raw["confidence"]
            reason = raw["reason"]
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError(
                "Analyse benötigt action, confidence und reason."
            ) from exc

        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0.0 <= confidence <= 1.0
        ):
            raise ValueError("Ungültige Confidence.")

        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Die Begründung fehlt.")

        result = {
            "action": action,
            "confidence": float(confidence),
            "reason": reason.strip(),
        }

        if require_approval:
            approved = raw.get("approved")

            if not isinstance(approved, bool):
                raise ValueError(
                    "Risk Analyst muss approved als Boolean liefern."
                )

            result["approved"] = approved

        return result

    def decide(
        self,
        market_data: Any,
        analyses: dict[str, Any],
    ) -> TradingDecision:
        ticker = str(
            self._get_value(market_data, "ticker", "UNKNOWN")
        )
        current_price = float(
            self._get_value(market_data, "current_price", 0.0)
        )

        def hold(
            reason: str,
            confidence: float = 0.0,
        ) -> TradingDecision:
            return TradingDecision(
                ticker=ticker,
                action=Action.HOLD,
                confidence=max(0.0, min(1.0, confidence)),
                reason=reason,
                current_price=max(0.0, current_price),
            )

        if current_price <= 0:
            return hold("Ungültiger Marktpreis.")

        aliases = {
            "technical analyst": ("Technical Analyst", "technical"),
            "risk analyst": ("Risk Analyst", "risk"),
            "portfolio analyst": ("Portfolio Analyst", "portfolio"),
        }

        normalized = {
            str(name).strip().casefold(): value
            for name, value in analyses.items()
        }

        parsed: dict[str, dict[str, Any]] = {}

        for role, names in aliases.items():
            raw = None

            for name in names:
                raw = normalized.get(name.casefold())
                if raw is not None:
                    break

            if raw is None:
                return hold(f"Analyse fehlt: {names[0]}.")

            try:
                parsed[role] = self._parse_analysis(
                    raw,
                    require_approval=(role == "risk analyst"),
                )
            except ValueError as exc:
                return hold(
                    f"Ungültige Analyse von {names[0]}: {exc}"
                )

        technical = parsed["technical analyst"]
        risk = parsed["risk analyst"]
        portfolio = parsed["portfolio analyst"]

        # Der Risk Analyst gibt nur eine Risikofreigabe.
        # Seine action ist ausdrücklich keine Handelsentscheidung.
        if risk["approved"] is not True:
            return hold(
                f"Keine Risikofreigabe: {risk['reason']}",
                min(risk["confidence"], technical["confidence"]),
            )

        if technical["action"] != portfolio["action"]:
            return hold(
                "Technische Analyse und Portfolioanalyse "
                "widersprechen sich."
            )

        if technical["action"] == Action.HOLD:
            return hold(
                "Die Agenten sehen derzeit kein eindeutiges Handelssignal.",
                min(
                    technical["confidence"],
                    risk["confidence"],
                    portfolio["confidence"],
                ),
            )

        confidence = min(
            technical["confidence"],
            risk["confidence"],
            portfolio["confidence"],
        )

        if confidence < self.min_confidence:
            return hold(
                f"Confidence {confidence:.2f} liegt unter dem "
                f"Mindestwert {self.min_confidence:.2f}.",
                confidence,
            )

        return TradingDecision(
            ticker=ticker,
            action=technical["action"],
            confidence=confidence,
            reason=(
                f"Technik: {technical['reason']} | "
                f"Risiko: {risk['reason']} | "
                f"Portfolio: {portfolio['reason']}"
            ),
            current_price=current_price,
        )
