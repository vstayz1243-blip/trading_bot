from typing import Any

from .client import Trading212Client


class Trading212History:
    """Handles historical Trading 212 orders and transactions."""

    def __init__(self, client: Trading212Client):
        self.client = client

    def get_orders(
        self,
        ticker: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Return one page of historical orders."""

        if not 1 <= limit <= 50:
            raise ValueError(
                "limit must be between 1 and 50."
            )

        params: dict[str, Any] = {
            "limit": limit,
        }

        if ticker is not None:
            params["ticker"] = ticker.upper()

        return self.client.get(
            "/equity/history/orders",
            params=params,
        )

    def get_transactions(
        self,
        limit: int = 50,
        time: str | None = None,
    ) -> dict[str, Any]:
        """Return one page of historical transactions."""

        if not 1 <= limit <= 50:
            raise ValueError(
                "limit must be between 1 and 50."
            )

        params: dict[str, Any] = {
            "limit": limit,
        }

        if time is not None:
            params["time"] = time

        return self.client.get(
            "/equity/history/transactions",
            params=params,
        )

    def get_all_orders(
        self,
        ticker: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch all historical orders."""

        first_page = self.get_orders(
            ticker=ticker,
            limit=limit,
        )

        orders = list(
            first_page.get("items", [])
        )

        next_page_path = first_page.get(
            "nextPagePath"
        )

        while next_page_path:
            page = self.client.get(
                next_page_path
            )

            orders.extend(
                page.get("items", [])
            )

            next_page_path = page.get(
                "nextPagePath"
            )

        return orders

    def get_all_transactions(
        self,
        limit: int = 50,
        time: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all historical transactions."""

        first_page = self.get_transactions(
            limit=limit,
            time=time,
        )

        transactions = list(
            first_page.get("items", [])
        )

        next_page_path = first_page.get(
            "nextPagePath"
        )

        while next_page_path:
            page = self.client.get(
                next_page_path
            )

            transactions.extend(
                page.get("items", [])
            )

            next_page_path = page.get(
                "nextPagePath"
            )

        return transactions