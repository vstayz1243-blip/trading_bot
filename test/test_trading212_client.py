
from unittest.mock import Mock

import pytest
import requests

from client.exceptions import (
    Trading212APIError,
    Trading212OrderStatusUnknown,
)
from client.trading212 import DEMO_BASE_URL, Trading212Client


def make_client():
    client = Trading212Client.__new__(Trading212Client)
    client.base_url = DEMO_BASE_URL
    client.max_retries = 3
    client.demo_orders_enabled = True
    client.session = Mock()
    return client


@pytest.mark.parametrize(
    "order_id",
    [None, True, False, 0, -1, "123", 123.0],
)
def test_stop_order_rejects_invalid_order_id(order_id):
    client = make_client()
    client.post = Mock(return_value={"id": order_id})

    with pytest.raises(Trading212OrderStatusUnknown):
        client.place_stop_order(
            ticker="AAPL_US_EQ",
            quantity=-2.0,
            stop_price=95.0,
        )

    client.post.assert_called_once()


def test_stop_order_rejects_missing_order_id():
    client = make_client()
    client.post = Mock(return_value={"status": "accepted"})

    with pytest.raises(Trading212OrderStatusUnknown):
        client.place_stop_order(
            ticker="AAPL_US_EQ",
            quantity=-2.0,
            stop_price=95.0,
        )

    client.post.assert_called_once()


def test_stop_order_accepts_valid_integer_id():
    client = make_client()
    expected = {"id": 123}
    client.post = Mock(return_value=expected)

    result = client.place_stop_order(
        ticker="AAPL_US_EQ",
        quantity=-2.0,
        stop_price=95.0,
    )

    assert result == expected
    client.post.assert_called_once_with(
        "/equity/orders/stop",
        json={
            "ticker": "AAPL_US_EQ",
            "quantity": -2.0,
            "stopPrice": 95.0,
            "timeValidity": "GOOD_TILL_CANCEL",
        },
    )


def test_post_timeout_is_not_retried():
    client = make_client()
    client.session.request.side_effect = requests.Timeout(
        "Simulierter Timeout"
    )

    with pytest.raises(Trading212OrderStatusUnknown):
        client.post(
            "/equity/orders/stop",
            json={
                "ticker": "AAPL_US_EQ",
                "quantity": -2.0,
                "stopPrice": 95.0,
                "timeValidity": "GOOD_TILL_CANCEL",
            },
        )

    assert client.session.request.call_count == 1


def test_post_server_error_is_not_retried():
    client = make_client()

    response = Mock()
    response.status_code = 500
    response.ok = False
    response.text = "Internal Server Error"
    client.session.request.return_value = response

    with pytest.raises(Trading212OrderStatusUnknown):
        client.post("/equity/orders/stop", json={})

    assert client.session.request.call_count == 1


def test_post_invalid_json_means_unknown_order_status():
    client = make_client()

    response = Mock()
    response.status_code = 200
    response.ok = True
    response.content = b"{invalid json"
    response.json.side_effect = ValueError("Invalid JSON")
    client.session.request.return_value = response

    with pytest.raises(Trading212OrderStatusUnknown):
        client.post("/equity/orders/stop", json={})

    assert client.session.request.call_count == 1


def test_get_retries_connection_error():
    client = make_client()

    response = Mock()
    response.status_code = 200
    response.ok = True
    response.content = b'{"orders": []}'
    response.json.return_value = {"orders": []}

    client.session.request.side_effect = [
        requests.ConnectionError("Temporärer Fehler"),
        response,
    ]

    # Verhindert Wartezeiten im Test.
    import client.trading212 as trading212_module

    original_sleep = trading212_module.time.sleep
    trading212_module.time.sleep = Mock()

    try:
        result = client.get("/equity/orders")
    finally:
        trading212_module.time.sleep = original_sleep

    assert result == {"orders": []}
    assert client.session.request.call_count == 2
