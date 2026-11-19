from typing import Any


def calculate_portfolio_metrics(
    positions: list[Any],
    account_cash: float,
    account_equity: float,
    account_currency: str,
    fx_rates_to_account: dict[str, float],
) -> dict[str, Any]:
    """Berechnet Portfolio-Kennzahlen in der Kontowährung."""

    account_currency = account_currency.upper()

    if account_cash < 0:
        raise ValueError("Der verfügbare Kontostand ist negativ.")

    if account_equity <= 0:
        raise ValueError("Die Kontoequity muss positiv sein.")

    position_metrics = []
    total_position_value = 0.0
    total_unrealized_pnl = 0.0
    unknown_currency_positions = 0

    for position in positions:
        ticker = position.ticker
        currency = str(position.currency).upper()
        quantity = float(position.quantity)
        current_price = float(position.current_price)
        average_price = float(position.average_price)

        if quantity < 0 or current_price < 0 or average_price < 0:
            raise ValueError(f"Ungültige Positionsdaten für {ticker}.")

        # FX-Rate bedeutet: 1 Einheit der Positionswährung
        # entspricht so vielen Einheiten der Kontowährung.
        if currency == account_currency:
            fx_rate = 1.0
        else:
            fx_rate = fx_rates_to_account.get(currency)

        if fx_rate is None or fx_rate <= 0:
            unknown_currency_positions += 1
            position_metrics.append({
                "ticker": ticker,
                "currency": currency,
                "position_value_native": quantity * current_price,
                "weight_percent": None,
                "unrealized_pnl": None,
                "fx_rate_to_account": None,
                "weight_calculable": False,
            })
            continue

        native_value = quantity * current_price
        native_cost = quantity * average_price

        position_value = native_value * fx_rate
        cost_basis = native_cost * fx_rate
        unrealized_pnl = position_value - cost_basis
        weight_percent = position_value / account_equity * 100

        total_position_value += position_value
        total_unrealized_pnl += unrealized_pnl

        position_metrics.append({
            "ticker": ticker,
            "currency": currency,
            "position_value_native": native_value,
            "position_value_account_currency": position_value,
            "cost_basis_account_currency": cost_basis,
            "unrealized_pnl": unrealized_pnl,
            "weight_percent": weight_percent,
            "fx_rate_to_account": fx_rate,
            "weight_calculable": True,
        })

    largest_position_weight = (
        max(
            (
                item["weight_percent"]
                for item in position_metrics
                if item["weight_percent"] is not None
            ),
            default=None,
        )
    )

    return {
        "account_currency": account_currency,
        "account_cash_available": account_cash,
        "account_equity": account_equity,
        "cash_available_percent": account_cash / account_equity * 100,
        "positions": position_metrics,
        "total_position_value_account_currency": total_position_value,
        "total_unrealized_pnl_account_currency": total_unrealized_pnl,
        "largest_position_weight_percent": largest_position_weight,
        "unknown_currency_positions": unknown_currency_positions,
        "all_position_weights_calculable": unknown_currency_positions == 0,
    }
