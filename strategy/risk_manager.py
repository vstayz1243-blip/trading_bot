
import math

from strategy.decision import Action, TradingDecision


class RiskManager:
    def __init__(
        self,
        max_order_value: float = 500.0,
        max_position_value: float = 1000.0,
    ) -> None:
        for name, value in (
            ("max_order_value", max_order_value),
            ("max_position_value", max_position_value),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(
                    f"{name} muss positiv und endlich sein."
                )

        self.max_order_value = float(max_order_value)
        self.max_position_value = float(max_position_value)

    def validate(
        self,
        decision: TradingDecision,
        current_price_account_currency: float,
        current_position_value: float,
        current_position_quantity: float,
        available_cash: float,
        order_quantity: float,
    ) -> tuple[bool, str]:
        if decision.action == Action.HOLD:
            return True, "HOLD - keine Order erforderlich."

        values = {
            "current_price_account_currency":
                current_price_account_currency,
            "current_position_value": current_position_value,
            "current_position_quantity": current_position_quantity,
            "available_cash": available_cash,
            "order_quantity": order_quantity,
        }

        for name, value in values.items():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                return False, f"Ungültiger Zahlenwert: {name}."

        if current_price_account_currency <= 0:
            return False, "Umgerechneter Aktienpreis ist ungültig."

        if current_position_value < 0:
            return False, "Positionswert darf nicht negativ sein."

        if current_position_quantity < 0:
            return False, "Positionsmenge darf nicht negativ sein."

        if available_cash < 0:
            return False, "Verfügbares Guthaben darf nicht negativ sein."

        if order_quantity <= 0:
            return False, "Ordermenge muss größer als 0 sein."

        order_value = (
            order_quantity * current_price_account_currency
        )

        if not math.isfinite(order_value) or order_value <= 0:
            return False, "Ungültiger Orderwert."

        if order_value > self.max_order_value + 1e-8:
            return False, (
                f"Orderwert {order_value:.2f} überschreitet das "
                f"Limit von {self.max_order_value:.2f} "
                f"in der Kontowährung."
            )

        if decision.action == Action.BUY:
            if order_value > available_cash + 1e-8:
                return False, "Nicht genügend verfügbares Guthaben."

            new_position_value = current_position_value + order_value

            if new_position_value > self.max_position_value + 1e-8:
                return False, (
                    f"Positionswert nach Kauf {new_position_value:.2f} "
                    f"überschreitet das Limit von "
                    f"{self.max_position_value:.2f}."
                )

        elif decision.action == Action.SELL:
            if order_quantity > current_position_quantity + 1e-8:
                return False, (
                    "Verkaufsmenge überschreitet den Bestand."
                )

            if order_value > current_position_value + 1e-8:
                return False, (
                    "Verkaufswert überschreitet den Positionswert."
                )

        else:
            return False, "Unbekannte Handelsaktion."

        return True, (
            f"{decision.action.value} hat die lokalen "
            f"Risikoprüfungen bestanden."
        )
