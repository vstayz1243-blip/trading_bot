from typing import Any

from .client import Trading212Client
from .orders import Trading212Orders


class Trading212Positions:
    """Handles open equity positions in Trading 212."""

    def __init__(
        self,
        client: Trading212Client,
        orders: Trading212Orders | None = None,
    ):
        self.client = client
        self.orders = orders or Trading212Orders(client)

    def get_all(self) -> list[dict[str, Any]]:
        """Return all currently open positions."""

        return self.client.get(
            "/equity/positions"
        )

    def get(
        self,
        ticker: str,
    ) -> dict[str, Any] | None:
        """Return an open position for a ticker."""

        ticker = ticker.upper()

        for position in self.get_all():
            if position.get("ticker") == ticker:
                return position

        return None

    def exists(self, ticker: str) -> bool:
        """Return True if an open position exists."""

        return self.get(ticker) is not None

    def quantity(self, ticker: str) -> float:
        """Return the current position quantity."""

        position = self.get(ticker)

        if position is None:
            return 0.0

        return float(
            position.get("quantity", 0)
        )

    def close(
        self,
        ticker: str,
    ) -> dict[str, Any]:
        """Close an existing position using a market order."""

        position = self.get(ticker)

        if position is None:
            raise ValueError(
                f"No open position found for '{ticker}'."
            )

        quantity = float(
            position.get("quantity", 0)
        )

        if quantity == 0:
            raise ValueError(
                f"Position '{ticker}' has zero quantity."
            )

        close_quantity = -quantity

        return self.orders.market_order(
            ticker=ticker,
            quantity=close_quantity,
        )