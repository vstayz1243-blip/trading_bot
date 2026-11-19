import json
from pathlib import Path
from typing import Any

import requests
from requests.auth import HTTPBasicAuth

from .exceptions import (
    Trading212AuthenticationError,
    Trading212BadRequestError,
    Trading212Error,
    Trading212NotFoundError,
    Trading212RateLimitError,
    Trading212ServerError,
)


class Trading212Client:
    """Low-level client for the Trading 212 REST API."""

    def __init__(
        self,
        credentials_path: str = "credentials.json",
        demo: bool = True,
    ):
        self.base_url = (
            "https://demo.trading212.com/api/v0"
            if demo
            else "https://live.trading212.com/api/v0"
        )

        self.credentials_path = Path(credentials_path)

        self.key, self.secret = self._load_credentials()

        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(
            self.key,
            self.secret,
        )

        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    def _load_credentials(self) -> tuple[str, str]:
        """Load API credentials from credentials.json."""

        if not self.credentials_path.exists():
            raise FileNotFoundError(
                f"Credentials file not found: "
                f"{self.credentials_path}"
            )

        with self.credentials_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            credentials = json.load(file)

        try:
            key = credentials["key"].strip()
            secret = credentials["secret"].strip()

        except KeyError as exc:
            raise ValueError(
                "credentials.json must contain "
                "'key' and 'secret'."
            ) from exc

        if not key or not secret:
            raise ValueError(
                "Trading 212 key and secret must not be empty."
            )

        return key, secret

    def _build_url(self, endpoint: str) -> str:
        """Build an API URL."""

        if endpoint.startswith("http://") or endpoint.startswith(
            "https://"
        ):
            return endpoint

        return f"{self.base_url}{endpoint}"

    def _handle_response(
        self,
        response: requests.Response,
    ) -> Any:
        """Validate an API response and map HTTP errors."""

        if response.ok:
            if not response.content:
                return None

            return response.json()

        status_code = response.status_code

        try:
            error_data = response.json()
        except ValueError:
            error_data = response.text

        message = (
            f"Trading 212 API error "
            f"({status_code}): {error_data}"
        )

        if status_code in (401, 403):
            raise Trading212AuthenticationError(message)

        if status_code == 400:
            raise Trading212BadRequestError(message)

        if status_code == 404:
            raise Trading212NotFoundError(message)

        if status_code == 429:
            raise Trading212RateLimitError(message)

        if 500 <= status_code <= 599:
            raise Trading212ServerError(message)

        raise Trading212Error(message)

    def get(
        self,
        endpoint: str,
        **kwargs,
    ) -> Any:
        """Send a GET request."""

        response = self.session.get(
            self._build_url(endpoint),
            **kwargs,
        )

        return self._handle_response(response)

    def post(
        self,
        endpoint: str,
        **kwargs,
    ) -> Any:
        """Send a POST request."""

        response = self.session.post(
            self._build_url(endpoint),
            **kwargs,
        )

        return self._handle_response(response)

    def delete(
        self,
        endpoint: str,
        **kwargs,
    ) -> Any:
        """Send a DELETE request."""

        response = self.session.delete(
            self._build_url(endpoint),
            **kwargs,
        )

        return self._handle_response(response)

    def get_account_summary(self) -> dict[str, Any]:
        """Return the current account summary."""

        return self.get(
            "/equity/account/summary"
        )