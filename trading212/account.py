from typing import Any

from .client import Trading212Client


class Trading212Account:
    """Handles Trading 212 account information."""

    def __init__(self, client: Trading212Client):
        self.client = client

    def get_summary(self) -> dict[str, Any]:
        """Return the current account summary."""

        return self.client.get(
            "/equity/account/summary"
        )