from typing import Any

from .client import Trading212Client


class Trading212Instruments:
    """Handles Trading 212 instrument metadata."""

    def __init__(self, client: Trading212Client):
        self.client = client
        self._instruments: list[dict[str, Any]] | None = None

    def get_all(
        self,
        refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Return all available instruments."""

        if self._instruments is None or refresh:
            self._instruments = self.client.get(
                "/equity/metadata/instruments"
            )

        return self._instruments

    def get(
        self,
        ticker: str,
    ) -> dict[str, Any] | None:
        """Return an instrument by ticker."""

        ticker = ticker.upper()

        for instrument in self.get_all():
            if instrument.get("ticker") == ticker:
                return instrument

        return None

    def exists(
        self,
        ticker: str,
    ) -> bool:
        """Return True if the ticker exists."""

        return self.get(ticker) is not None

    def get_by_isin(
        self,
        isin: str,
    ) -> dict[str, Any] | None:
        """Return an instrument by ISIN."""

        isin = isin.upper()

        for instrument in self.get_all():
            if instrument.get("isin") == isin:
                return instrument

        return None

    def get_by_type(
        self,
        instrument_type: str,
    ) -> list[dict[str, Any]]:
        """Return instruments of a specific type."""

        instrument_type = instrument_type.upper()

        return [
            instrument
            for instrument in self.get_all()
            if instrument.get("type") == instrument_type
        ]

    def search(
        self,
        query: str,
    ) -> list[dict[str, Any]]:
        """Search instruments by common identifying fields."""

        query = query.lower()

        return [
            instrument
            for instrument in self.get_all()
            if (
                query in str(
                    instrument.get("ticker", "")
                ).lower()
                or query in str(
                    instrument.get("name", "")
                ).lower()
                or query in str(
                    instrument.get("shortName", "")
                ).lower()
                or query in str(
                    instrument.get("isin", "")
                ).lower()
            )
        ]

    def clear_cache(self) -> None:
        """Clear the local instrument cache."""

        self._instruments = None