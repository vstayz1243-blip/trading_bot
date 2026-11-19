from typing import Any

from .client import Trading212Client
from .instruments import Trading212Instruments
from .orders import Trading212Orders
from .positions import Trading212Positions


class Trading212Execution:
    """
    High-level execution layer between strategy and Trading 212.

    This class is responsible for:
    - validating instruments
    - enforcing order limits
    - preventing duplicate pending orders
    - supporting dry-run mode
    - executing BUY / SELL orders
    - closing positions
    """

    def __init__(
        self,
        client: Trading212Client,
        dry_run: bool = True,
        max_quantity: float = 100.0,
        max_order_value: float | None = None,
        allow_duplicate_orders: bool = False,
        extended_hours: bool = False,
    ):
        self.client = client

        self.orders = Trading212Orders(client)
        self.positions = Trading212Positions(
            client,
            orders=self.orders,
        )
        self.instruments = Trading212Instruments(client)

        self.dry_run = dry_run
        self.max_quantity = max_quantity
        self.max_order_value = max_order_value
        self.allow_duplicate_orders = allow_duplicate_orders
        self.extended_hours = extended_hours

        if max_quantity <= 0:
            raise ValueError(
                "max_quantity must be greater than zero."
            )

        if max_order_value is not None and max_order_value <= 0:
            raise ValueError(
                "max_order_value must be greater than zero."
            )

    def buy(
        self,
        ticker: str,
        quantity: float,
        reference_price: float | None = None,
    ) -> dict[str, Any]:
        """
        Execute a BUY order.

        quantity must be positive.
        """

        if quantity <= 0:
            raise ValueError(
                "BUY quantity must be greater than zero."
            )

        return self._execute(
            ticker=ticker,
            quantity=quantity,
            reference_price=reference_price,
        )

    def sell(
        self,
        ticker: str,
        quantity: float,
        reference_price: float | None = None,
    ) -> dict[str, Any]:
        """
        Execute a SELL order.

        quantity is provided as a positive number here.
        Trading 212 receives it as a negative quantity.
        """

        if quantity <= 0:
            raise ValueError(
                "SELL quantity must be greater than zero."
            )

        return self._execute(
            ticker=ticker,
            quantity=-quantity,
            reference_price=reference_price,
        )

    def close_position(
        self,
        ticker: str,
    ) -> dict[str, Any]:
        """
        Close the complete existing position.

        This intentionally bypasses max_quantity because the
        purpose is to close an already existing position.
        """

        ticker = self._validate_ticker(ticker)

        position = self.positions.get(ticker)

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

        if self._has_pending_order(ticker):
            raise RuntimeError(
                f"Pending order already exists for '{ticker}'."
            )

        result = {
            "dry_run": self.dry_run,
            "action": "CLOSE",
            "ticker": ticker,
            "quantity": close_quantity,
        }

        if self.dry_run:
            return result

        order = self.orders.market_order(
            ticker=ticker,
            quantity=close_quantity,
            extended_hours=self.extended_hours,
        )

        result["order"] = order

        return result

    def _execute(
        self,
        ticker: str,
        quantity: float,
        reference_price: float | None = None,
    ) -> dict[str, Any]:
        """
        Validate and execute a market order.
        """

        ticker = self._validate_ticker(ticker)

        if quantity == 0:
            raise ValueError(
                "Order quantity must not be zero."
            )

        absolute_quantity = abs(quantity)

        self._validate_quantity(
            absolute_quantity
        )

        self._validate_order_value(
            absolute_quantity,
            reference_price,
        )

        if self._has_pending_order(ticker):
            raise RuntimeError(
                f"Pending order already exists for '{ticker}'."
            )

        action = (
            "BUY"
            if quantity > 0
            else "SELL"
        )

        result = {
            "dry_run": self.dry_run,
            "action": action,
            "ticker": ticker,
            "quantity": quantity,
        }

        if reference_price is not None:
            result["reference_price"] = reference_price
            result["estimated_value"] = (
                absolute_quantity * reference_price
            )

        if self.dry_run:
            return result

        order = self.orders.market_order(
            ticker=ticker,
            quantity=quantity,
            extended_hours=self.extended_hours,
        )

        result["order"] = order

        return result

    def _validate_ticker(
        self,
        ticker: str,
    ) -> str:
        """Validate that the ticker exists."""

        if not ticker or not ticker.strip():
            raise ValueError(
                "Ticker must not be empty."
            )

        ticker = ticker.strip().upper()

        instrument = self.instruments.get(
            ticker
        )

        if instrument is None:
            raise ValueError(
                f"Unknown Trading 212 ticker: '{ticker}'."
            )

        return ticker

    def _validate_quantity(
        self,
        quantity: float,
    ) -> None:
        """Validate maximum order quantity."""

        if quantity > self.max_quantity:
            raise ValueError(
                f"Order quantity {quantity} exceeds "
                f"maximum allowed quantity "
                f"{self.max_quantity}."
            )

    def _validate_order_value(
        self,
        quantity: float,
        reference_price: float | None,
    ) -> None:
        """
        Validate maximum estimated order value.

        If max_order_value is configured, a reference price
        is required.
        """

        if self.max_order_value is None:
            return

        if reference_price is None:
            raise ValueError(
                "reference_price is required when "
                "max_order_value is configured."
            )

        if reference_price <= 0:
            raise ValueError(
                "reference_price must be greater than zero."
            )

        estimated_value = (
            quantity * reference_price
        )

        if estimated_value > self.max_order_value:
            raise ValueError(
                f"Estimated order value "
                f"{estimated_value:.2f} exceeds "
                f"maximum allowed value "
                f"{self.max_order_value:.2f}."
            )

    def _has_pending_order(
        self,
        ticker: str,
    ) -> bool:
        """Check whether a pending order already exists."""

        if self.allow_duplicate_orders:
            return False

        pending_orders = self.orders.get_all()

        for order in pending_orders:
            if order.get("ticker") != ticker:
                continue

            status = str(
                order.get("status", "")
            ).upper()

            if status in {
                "LOCAL",
                "UNCONFIRMED",
                "CONFIRMED",
                "NEW",
                "PARTIALLY_FILLED",
                "REPLACING",
                "CANCELLING",
            }:
                return True

        return False