
from typing import Any


def calculate_portfolio_metrics(
    positions: list[Any],
    account_cash: float,
    account_equity: float,
    account_currency: str,
) -> dict[str, Any]:
    """
    Berechnet Portfolio-Kennzahlen aus vorhandenen Positionsdaten.

    Positionswerte in einer anderen Währung als der Kontowährung
    werden nicht ungeprüft mit der Kontoequity verglichen.
    """
    if account_cash < 0:
        raise ValueError("Der verfügbare Kontostand ist negativ.")

    if account_equity <= 0:
        raise ValueError("Die Kontoequity muss positiv sein.")

    normalized_account_currency = account_currency.upper()

    position_metrics = []
    known_values_in_account_currency = 0.0
    unknown_currency_positions = 0

    for position in positions:
        ticker = getattr(position, "ticker", "UNKNOWN")
        quantity = float(getattr(position, "quantity", 0.0))
        current_price = float(
            getattr(position, "current_price", 0.0)
        )
        average_price = float(
            getattr(position, "average_price", 0.0)
        )
        currency = str(
            getattr(position, "currency", "UNKNOWN")
        ).upper()

        if quantity < 0 or current_price < 0 or average_price < 0:
            raise ValueError(
                f"Ungültige Positionsdaten für {ticker}."
            )

        position_value = quantity * current_price
        cost_basis = quantity * average_price
        unrealized_pnl = position_value - cost_basis

        currency_matches = currency == normalized_account_currency

        if currency_matches:
            known_values_in_account_currency += position_value
            weight_percent = (
                position_value / account_equity
            ) * 100
        else:
            unknown_currency_positions += 1
            weight_percent = None

        position_metrics.append(
            {
                "ticker": ticker,
                "currency": currency,
                "quantity": quantity,
                "position_value": position_value,
                "cost_basis": cost_basis,
                "unrealized_pnl": unrealized_pnl,
                "weight_percent": weight_percent,
                "weight_calculable": currency_matches,
            }
        )

    cash_percent = (account_cash / account_equity) * 100

    return {
        "account_currency": normalized_account_currency,
        "account_cash": account_cash,
        "account_equity": account_equity,
        "cash_percent": cash_percent,
        "positions": position_metrics,
        "known_position_value_in_account_currency": (
            known_values_in_account_currency
        ),
        "unknown_currency_positions": unknown_currency_positions,
        "all_position_weights_calculable": (
            unknown_currency_positions == 0
        ),
    }
