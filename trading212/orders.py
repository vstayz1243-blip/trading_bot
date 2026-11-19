from typing import Any

from .client import Trading212Client


class Trading212Orders:
    """Handles order operations in Trading 212."""

    def __init__(self, client: Trading212Client):
        self.client = client

    def market_order(
        self,
        ticker: str,
        quantity: float,
        extended_hours: bool = False,
    ) -> dict[str, Any]:
        """
        Create a market order.

        Positive quantity = BUY
        Negative quantity = SELL
        """

        self._validate_quantity(quantity)

        return self.client.post(
            "/equity/orders/market",
            json={
                "ticker": ticker.upper(),
                "quantity": quantity,
                "extendedHours": extended_hours,
            },
        )

    def limit_order(
        self,
        ticker: str,
        quantity: float,
        limit_price: float,
        time_validity: str = "DAY",
    ) -> dict[str, Any]:
        """Create a limit order."""

        self._validate_quantity(quantity)

        if limit_price <= 0:
            raise ValueError(
                "limit_price must be greater than zero."
            )

        if time_validity not in {
            "DAY",
            "GOOD_TILL_CANCEL",
        }:
            raise ValueError(
                "time_validity must be "
                "'DAY' or 'GOOD_TILL_CANCEL'."
            )

        return self.client.post(
            "/equity/orders/limit",
            json={
                "ticker": ticker.upper(),
                "quantity": quantity,
                "limitPrice": limit_price,
                "timeValidity": time_validity,
            },
        )

    def stop_order(
        self,
        ticker: str,
        quantity: float,
        stop_price: float,
        time_validity: str = "DAY",
    ) -> dict[str, Any]:
        """Create a stop order."""

        self._validate_quantity(quantity)

        if stop_price <= 0:
            raise ValueError(
                "stop_price must be greater than zero."
            )

        if time_validity not in {
            "DAY",
            "GOOD_TILL_CANCEL",
        }:
            raise ValueError(
                "time_validity must be "
                "'DAY' or 'GOOD_TILL_CANCEL'."
            )

        return self.client.post(
            "/equity/orders/stop",
            json={
                "ticker": ticker.upper(),
                "quantity": quantity,
                "stopPrice": stop_price,
                "timeValidity": time_validity,
            },
        )

    def stop_limit_order(
        self,
        ticker: str,
        quantity: float,
        stop_price: float,
        limit_price: float,
        time_validity: str = "DAY",
    ) -> dict[str, Any]:
        """Create a stop-limit order."""

        self._validate_quantity(quantity)

        if stop_price <= 0:
            raise ValueError(
                "stop_price must be greater than zero."
            )

        if limit_price <= 0:
            raise ValueError(
                "limit_price must be greater than zero."
            )

        if time_validity not in {
            "DAY",
            "GOOD_TILL_CANCEL",
        }:
            raise ValueError(
                "time_validity must be "
                "'DAY' or 'GOOD_TILL_CANCEL'."
            )

        return self.client.post(
            "/equity/orders/stop_limit",
            json={
                "ticker": ticker.upper(),
                "quantity": quantity,
                "stopPrice": stop_price,
                "limitPrice": limit_price,
                "timeValidity": time_validity,
            },
        )

    def get(
        self,
        order_id: int,
    ) -> dict[str, Any]:
        """Return an order by ID."""

        return self.client.get(
            f"/equity/orders/{order_id}"
        )

    def get_all(self) -> list[dict[str, Any]]:
        """Return all currently pending orders."""

        return self.client.get(
            "/equity/orders"
        )

    def cancel(
        self,
        order_id: int,
    ):
        """Cancel an existing order."""

        return self.client.delete(
            f"/equity/orders/{order_id}"
        )

    @staticmethod
    def _validate_quantity(
        quantity: float,
    ) -> None:
        if quantity == 0:
            raise ValueError(
                "Order quantity must not be zero."
            )