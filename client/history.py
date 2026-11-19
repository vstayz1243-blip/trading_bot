
from typing import Any

from client.trading212 import Trading212Client


class HistoryClient:
    """Read-only-Zugriff auf die Trading212-Historie."""

    def __init__(self, client: Trading212Client) -> None:
        self.client = client

    def get_orders(self, limit: int = 50) -> Any:
        """Gibt die rohe API-Antwort der Orderhistorie zurück."""
        self._validate_limit(limit)

        return self.client.get(
            "/equity/history/orders",
            params={"limit": limit},
        )

    def get_order_items(self, limit: int = 50) -> list[dict[str, Any]]:
        """Extrahiert historische Orders aus dem bekannten API-Format."""
        response = self.get_orders(limit=limit)

        if not isinstance(response, dict):
            raise ValueError(
                "Die Orderhistorie ist kein JSON-Objekt."
            )

        items = response.get("items")

        if not isinstance(items, list):
            raise ValueError(
                "Die Orderhistorie enthält keine gültige 'items'-Liste."
            )

        if not all(isinstance(item, dict) for item in items):
            raise ValueError(
                "Die Orderhistorie enthält ungültige Einträge."
            )

        return items

    def get_transactions(self, limit: int = 50) -> Any:
        """Gibt die rohe API-Antwort der Transaktionshistorie zurück."""
        self._validate_limit(limit)

        return self.client.get(
            "/equity/history/transactions",
            params={"limit": limit},
        )

    @staticmethod
    def _validate_limit(limit: int) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit muss eine Ganzzahl sein.")

        if not 1 <= limit <= 50:
            raise ValueError("limit muss zwischen 1 und 50 liegen.")
