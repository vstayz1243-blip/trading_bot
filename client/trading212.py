
import json
import time
from math import isfinite
from pathlib import Path
from typing import Any

import requests
from requests.auth import HTTPBasicAuth

from client.exceptions import (
    Trading212AuthenticationError,
    Trading212APIError,
    Trading212ConnectionError,
    Trading212OrderStatusUnknown,
)


DEMO_BASE_URL = "https://demo.trading212.com/api/v0"


class Trading212Client:
    """
    Trading-212-Client ausschließlich für die Demo-API.

    Orderausführung erfordert eine explizite Freigabe.
    Schreibende Requests werden niemals automatisch wiederholt,
    da der Ausgang einer Order bei Netzwerkfehlern unklar sein kann.
    """

    def __init__(
        self,
        credentials_path: str = "credentials.json",
        base_url: str = DEMO_BASE_URL,
        max_retries: int = 3,
        demo_orders_enabled: bool = False,
    ) -> None:
        normalized_url = base_url.rstrip("/")

        if normalized_url != DEMO_BASE_URL:
            raise ValueError(
                "Sicherheitsabbruch: Dieser Client erlaubt ausschließlich "
                "die Trading-212-Demo-API."
            )

        if not isinstance(demo_orders_enabled, bool):
            raise TypeError("demo_orders_enabled muss bool sein.")

        if (
            isinstance(max_retries, bool)
            or not isinstance(max_retries, int)
            or max_retries < 0
        ):
            raise ValueError(
                "max_retries muss eine nicht-negative Ganzzahl sein."
            )

        self.base_url = normalized_url
        self.credentials_path = Path(credentials_path)
        self.max_retries = max_retries
        self.demo_orders_enabled = demo_orders_enabled

        self.session = requests.Session()
        self._load_credentials()

    # ---------------------------------------------------------
    # Credentials
    # ---------------------------------------------------------

    def _load_credentials(self) -> None:
        if not self.credentials_path.exists():
            raise FileNotFoundError(
                f"Credentials file not found: {self.credentials_path}"
            )

        try:
            with self.credentials_path.open("r", encoding="utf-8") as file:
                credentials = json.load(file)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "credentials.json enthält ungültiges JSON."
            ) from exc

        if not isinstance(credentials, dict):
            raise ValueError(
                "credentials.json muss ein JSON-Objekt enthalten."
            )

        try:
            api_key = credentials["key"]
            api_secret = credentials["secret"]
        except KeyError as exc:
            raise ValueError(
                "credentials.json muss 'key' und 'secret' enthalten."
            ) from exc

        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("Der API-Key ist ungültig.")

        if not isinstance(api_secret, str) or not api_secret.strip():
            raise ValueError("Das API-Secret ist ungültig.")

        self.session.auth = HTTPBasicAuth(api_key, api_secret)
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    # ---------------------------------------------------------
    # HTTP Request
    # ---------------------------------------------------------

    def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> Any:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        method = method.upper()

        # Nur GET darf automatisch wiederholt werden.
        retryable = method == "GET"
        attempts = self.max_retries + 1 if retryable else 1

        for attempt in range(attempts):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    timeout=30,
                    **kwargs,
                )
            except requests.RequestException as exc:
                if not retryable:
                    raise Trading212OrderStatusUnknown(
                        f"{method} {endpoint}: Verbindung unterbrochen. "
                        "Der Ausgang der Anfrage ist unklar. "
                        "Vor weiteren Orders den tatsächlichen Status prüfen."
                    ) from exc

                if attempt >= attempts - 1:
                    raise Trading212ConnectionError(
                        "Verbindung zu Trading 212 fehlgeschlagen."
                    ) from exc

                time.sleep(min(2**attempt, 10))
                continue

            if response.status_code == 429:
                if not retryable or attempt >= attempts - 1:
                    raise Trading212APIError(
                        "Trading-212-Rate-Limit aktiv. "
                        "Die Anfrage wurde nicht automatisch erneut gesendet."
                    )

                retry_after = response.headers.get("Retry-After")

                try:
                    wait_seconds = (
                        max(0.0, float(retry_after))
                        if retry_after is not None
                        else min(5.0 * (2**attempt), 30.0)
                    )
                except (TypeError, ValueError):
                    wait_seconds = min(5.0 * (2**attempt), 30.0)

                time.sleep(wait_seconds)
                continue

            if response.status_code in (401, 403):
                raise Trading212AuthenticationError(
                    "Trading-212-Authentifizierung fehlgeschlagen."
                )

            # Bei schreibenden Requests bedeutet 408 nicht zuverlässig,
            # dass die Order nicht verarbeitet wurde.
            if response.status_code == 408 and not retryable:
                raise Trading212OrderStatusUnknown(
                    f"{method} {endpoint}: HTTP 408 Request Timeout. "
                    "Der Ausgang der Anfrage ist unklar. "
                    "Keine automatische Wiederholung."
                )

            if not response.ok:
                if not retryable and response.status_code >= 500:
                    raise Trading212OrderStatusUnknown(
                        f"{method} {endpoint}: HTTP "
                        f"{response.status_code}. Der Ausgang der Anfrage "
                        "ist unklar. Keine automatische Wiederholung."
                    )

                raise Trading212APIError(
                    f"Trading 212 API antwortete mit "
                    f"{response.status_code}: {response.text}"
                )

            if not response.content:
                return None

            try:
                return response.json()
            except ValueError as exc:
                if not retryable:
                    raise Trading212OrderStatusUnknown(
                        f"{method} {endpoint}: Erfolgreiche HTTP-Antwort, "
                        "aber ungültiges JSON. Der Ausgang der Aktion "
                        "muss geprüft werden."
                    ) from exc

                raise Trading212APIError(
                    "Trading 212 lieferte ungültiges JSON."
                ) from exc

        raise Trading212APIError(
            "Trading-212-Anfrage unerwartet fehlgeschlagen."
        )

    # ---------------------------------------------------------
    # HTTP Methods
    # ---------------------------------------------------------

    def get(self, endpoint: str, **kwargs: Any) -> Any:
        return self._request("GET", endpoint, **kwargs)

    def post(self, endpoint: str, **kwargs: Any) -> Any:
        return self._request("POST", endpoint, **kwargs)

    def delete(self, endpoint: str, **kwargs: Any) -> Any:
        return self._request("DELETE", endpoint, **kwargs)

    # ---------------------------------------------------------
    # Account / Instruments / Positions / Orders
    # ---------------------------------------------------------

    def get_account_summary(self) -> dict[str, Any]:
        account = self.get("/equity/account/summary")

        if not isinstance(account, dict):
            raise Trading212APIError(
                "Trading 212 lieferte keine gültigen Kontodaten."
            )

        return account

    def get_instruments(self) -> list[dict[str, Any]]:
        instruments = self.get("/equity/metadata/instruments")

        if not isinstance(instruments, list):
            raise Trading212APIError(
                "Trading 212 lieferte keine gültige Instrumentenliste."
            )

        if not all(isinstance(item, dict) for item in instruments):
            raise Trading212APIError(
                "Die Instrumentenliste enthält ungültige Einträge."
            )

        return instruments

    def get_positions(self) -> list[dict[str, Any]]:
        positions = self.get("/equity/positions")

        if not isinstance(positions, list):
            raise Trading212APIError(
                "Trading 212 lieferte keine gültige Positionsliste."
            )

        if not all(isinstance(item, dict) for item in positions):
            raise Trading212APIError(
                "Die Positionsliste enthält ungültige Einträge."
            )

        return positions

    def get_pending_orders(self) -> list[dict[str, Any]]:
        orders = self.get("/equity/orders")

        if not isinstance(orders, list):
            raise Trading212APIError(
                "Trading 212 lieferte keine gültige Liste offener Orders."
            )

        if not all(isinstance(order, dict) for order in orders):
            raise Trading212APIError(
                "Die Orderliste enthält ungültige Einträge."
            )

        return orders

    def get_order(self, order_id: int) -> dict[str, Any]:
        if (
            isinstance(order_id, bool)
            or not isinstance(order_id, int)
            or order_id <= 0
        ):
            raise ValueError("Order-ID muss eine positive Ganzzahl sein.")

        order = self.get(f"/equity/orders/{order_id}")

        if not isinstance(order, dict):
            raise Trading212APIError(
                "Trading 212 lieferte keine gültige Orderantwort."
            )

        return order

    # ---------------------------------------------------------
    # Order Safety
    # ---------------------------------------------------------

    def _require_demo_order_permission(self) -> None:
        if self.base_url != DEMO_BASE_URL:
            raise RuntimeError(
                "Sicherheitsabbruch: keine Demo-API."
            )

        if not self.demo_orders_enabled:
            raise RuntimeError(
                "Order blockiert: Demo-Orderausführung ist nicht freigeschaltet."
            )

    @staticmethod
    def _validate_ticker(ticker: str) -> None:
        if not isinstance(ticker, str) or not ticker.strip():
            raise ValueError("Ticker darf nicht leer sein.")

    @staticmethod
    def _validate_quantity(
        quantity: float,
        allow_negative: bool = True,
    ) -> None:
        if (
            isinstance(quantity, bool)
            or not isinstance(quantity, (int, float))
            or not isfinite(quantity)
            or quantity == 0
        ):
            raise ValueError(
                "Quantity muss eine endliche Zahl ungleich 0 sein."
            )

        if not allow_negative and quantity < 0:
            raise ValueError("Quantity darf nicht negativ sein.")

    def place_market_order(
        self,
        ticker: str,
        quantity: float,
        extended_hours: bool = False,
    ) -> dict[str, Any]:
        self._require_demo_order_permission()
        self._validate_ticker(ticker)
        self._validate_quantity(quantity)

        if not isinstance(extended_hours, bool):
            raise TypeError("extended_hours muss bool sein.")

        payload = {
            "ticker": ticker,
            "quantity": quantity,
            "extendedHours": extended_hours,
        }

        result = self.post("/equity/orders/market", json=payload)

        if not isinstance(result, dict):
            raise Trading212APIError(
                "Marktorder lieferte keine eindeutige JSON-Orderantwort."
            )

        return result

    def place_stop_order(
        self,
        ticker: str,
        quantity: float,
        stop_price: float,
        time_validity: str = "GOOD_TILL_CANCEL",
    ) -> dict[str, Any]:
        self._require_demo_order_permission()
        self._validate_ticker(ticker)
        self._validate_quantity(quantity)

        if quantity >= 0:
            raise ValueError(
                "Eine Stop-Loss-Verkaufsorder benötigt eine negative Menge."
            )

        if (
            isinstance(stop_price, bool)
            or not isinstance(stop_price, (int, float))
            or not isfinite(stop_price)
            or stop_price <= 0
        ):
            raise ValueError("Stop-Preis muss positiv und endlich sein.")

        if time_validity not in {"DAY", "GOOD_TILL_CANCEL"}:
            raise ValueError("Ungültige time_validity.")

        payload = {
            "ticker": ticker,
            "quantity": quantity,
            "stopPrice": stop_price,
            "timeValidity": time_validity,
        }


        result = self.post("/equity/orders/stop", json=payload)

        if not isinstance(result, dict):
            raise Trading212OrderStatusUnknown(
                "Stop-Order lieferte keine eindeutige JSON-Orderantwort. "
                "Orderstatus manuell prüfen; keine weitere Order senden."
            )

        order_id = result.get("id")

        if (
            isinstance(order_id, bool)
            or not isinstance(order_id, int)
            or order_id <= 0
        ):
            raise Trading212OrderStatusUnknown(
                "Stop-Order-Antwort enthält keine gültige Order-ID. "
                "Die Order könnte bereits erstellt worden sein. "
                "Orderstatus manuell prüfen; keine weitere Order senden."
            )

        return result


    def cancel_order(self, order_id: int) -> Any:
        self._require_demo_order_permission()

        if (
            isinstance(order_id, bool)
            or not isinstance(order_id, int)
            or order_id <= 0
        ):
            raise ValueError("Order-ID muss eine positive Ganzzahl sein.")

        # Die Rückgabe bestätigt nicht automatisch, dass die Order
        # endgültig storniert wurde. Anschließend Status prüfen.
        return self.delete(f"/equity/orders/{order_id}")

    # ---------------------------------------------------------
    # Cleanup
    # ---------------------------------------------------------

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "Trading212Client":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
