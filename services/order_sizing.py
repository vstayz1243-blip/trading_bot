import math
from dataclasses import replace
from typing import Any

from config.risk_limits import RISK_LIMITS
from strategy.decision import Action, TradingDecision
from strategy.risk_manager import RiskManager


def _is_valid_number(value: Any) -> bool:
    """Return True for finite numeric values, excluding booleans."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


class OrderSizingService:
    """Calculate order quantities and apply deterministic risk validation.

    This service prepares decisions only. It never submits orders.
    """

    def __init__(
        self,
        max_order_value: float = RISK_LIMITS.max_order_value,
        quantity_precision: int = RISK_LIMITS.quantity_precision,
    ) -> None:
        if (
            isinstance(max_order_value, bool)
            or not isinstance(max_order_value, (int, float))
            or not math.isfinite(max_order_value)
            or max_order_value <= 0
        ):
            raise ValueError("max_order_value must be positive and finite.")

        if (
            isinstance(quantity_precision, bool)
            or not isinstance(quantity_precision, int)
            or quantity_precision < 0
        ):
            raise ValueError("quantity_precision must be a non-negative integer.")

        self.max_order_value = float(max_order_value)
        self.quantity_precision = quantity_precision

    def prepare_order(
        self,
        decision: TradingDecision,
        market_data: Any,
        risk_manager: RiskManager,
    ) -> tuple[TradingDecision | None, str]:
        """Size an order and ask RiskManager for final deterministic approval."""
        if decision.action == Action.HOLD:
            return None, "HOLD - keine Order erforderlich."

        price = market_data.current_price
        fx_rate = market_data.fx_rate_to_account
        available_cash = market_data.account_cash

        for name, value in (
            ("aktueller Kurs", price),
            ("Wechselkurs", fx_rate),
            ("verfügbares Guthaben", available_cash),
        ):
            if not _is_valid_number(value):
                return None, f"Ungültiger oder fehlender Wert: {name}."

        if price <= 0:
            return None, "Der aktuelle Kurs muss größer als null sein."

        if fx_rate <= 0:
            return None, "Der Wechselkurs muss größer als null sein."

        if available_cash < 0:
            return None, "Verfügbares Guthaben darf nicht negativ sein."

        account_price = price * fx_rate

        if not _is_valid_number(account_price) or account_price <= 0:
            return None, "Berechneter Kurs in Kontowährung ist ungültig."

        positions = getattr(market_data, "positions", None)

        if not isinstance(positions, list):
            return None, "Positionsdaten fehlen oder sind ungültig."

        matching_positions = [
            position
            for position in positions
            if getattr(position, "ticker", None) == decision.ticker
        ]

        if len(matching_positions) > 1:
            return None, "Mehrere passende Positionen gefunden."

        position = matching_positions[0] if matching_positions else None

        raw_quantity = (
            getattr(position, "quantity", None)
            if position is not None
            else 0.0
        )

        if not _is_valid_number(raw_quantity):
            return None, "Ungültige Menge der bestehenden Position."

        position_quantity = abs(raw_quantity)

        raw_position_price = (
            getattr(position, "current_price", None)
            if position is not None
            else price
        )

        if (
            not _is_valid_number(raw_position_price)
            or raw_position_price <= 0
        ):
            return None, "Ungültiger Kurs der bestehenden Position."

        current_position_value = (
            position_quantity * raw_position_price * fx_rate
        )

        if (
            not _is_valid_number(current_position_value)
            or current_position_value < 0
        ):
            return None, "Wert der bestehenden Position ist ungültig."

        if decision.action == Action.BUY:
            order_value = min(self.max_order_value, available_cash)

            if order_value <= 0:
                return None, "Kein verfügbares Guthaben für einen Kauf."

            quantity = round(
                order_value / account_price,
                self.quantity_precision,
            )

        elif decision.action == Action.SELL:
            if position_quantity <= 0:
                return None, "Keine bestehende Position zum Verkaufen."

            quantity = round(
                position_quantity,
                self.quantity_precision,
            )

        else:
            return None, f"Unbekannte Aktion: {decision.action}"

        if not _is_valid_number(quantity) or quantity <= 0:
            return None, "Berechnete Ordermenge ist ungültig."

        actual_order_value = quantity * account_price

        if not _is_valid_number(actual_order_value):
            return None, "Berechneter Orderwert ist ungültig."

        if decision.action == Action.BUY:
            if actual_order_value > available_cash:
                return None, "Orderwert überschreitet das verfügbare Guthaben."

            if actual_order_value > self.max_order_value:
                return None, "Orderwert überschreitet das Orderlimit."

        approved, validation_message = risk_manager.validate(
            decision=decision,
            current_price_account_currency=account_price,
            current_position_value=current_position_value,
            current_position_quantity=position_quantity,
            available_cash=available_cash,
            order_quantity=quantity,
        )

        if not approved:
            return None, validation_message

        return replace(decision, quantity=quantity), validation_message
