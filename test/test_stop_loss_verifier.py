
import pytest

from services.stop_loss_verifier import StopLossVerifier


@pytest.fixture
def verifier():
    return StopLossVerifier()


def valid_stop_order(**overrides):
    order = {
        "ticker": "AAPL_US_EQ",
        "quantity": -0.1,
        "filledQuantity": 0,
        "stopPrice": 180.0,
        "side": "SELL",
        "status": "NEW",
        "type": "STOP",
    }
    order.update(overrides)
    return order


def test_no_orders_means_missing(verifier):
    result = verifier.verify("AAPL_US_EQ", 0.1, 200.0, [])

    assert result.status == "MISSING"
    assert result.approved is False


def test_invalid_position_means_unknown(verifier):
    result = verifier.verify("AAPL_US_EQ", 0, 200.0, [])

    assert result.status == "UNKNOWN"
    assert result.approved is False


def test_invalid_order_entry_means_unknown(verifier):
    result = verifier.verify(
        "AAPL_US_EQ",
        0.1,
        200.0,
        ["invalid order"],
    )

    assert result.status == "UNKNOWN"
    assert result.approved is False


def test_unrelated_order_does_not_protect_position(verifier):
    result = verifier.verify(
        "AAPL_US_EQ",
        0.1,
        200.0,
        [
            valid_stop_order(ticker="MSFT_US_EQ"),
        ],
    )

    assert result.status == "MISSING"
    assert result.approved is False


def test_missing_order_type_means_unknown(verifier):
    order = valid_stop_order()
    del order["type"]

    result = verifier.verify(
        "AAPL_US_EQ",
        0.1,
        200.0,
        [order],
    )

    assert result.status == "UNKNOWN"
    assert result.approved is False


def test_invalid_quantity_means_unknown(verifier):
    result = verifier.verify(
        "AAPL_US_EQ",
        0.1,
        200.0,
        [valid_stop_order(quantity="invalid")],
    )

    assert result.status == "UNKNOWN"
    assert result.approved is False


def test_matching_stop_order_is_verified(verifier):
    result = verifier.verify(
        "AAPL_US_EQ",
        0.1,
        200.0,
        [valid_stop_order()],
    )

    assert result.status == "VERIFIED"
    assert result.approved is True

def test_partial_stop_coverage_means_missing(verifier):
    result = verifier.verify(
        "AAPL_US_EQ",
        0.2,
        200.0,
        [valid_stop_order()],
    )

    assert result.status == "MISSING"
    assert result.approved is False


@pytest.mark.parametrize(
    "stop_price",
    [0, 200.0, 210.0],
)
def test_invalid_stop_price_means_unknown(verifier, stop_price):
    result = verifier.verify(
        "AAPL_US_EQ",
        0.1,
        200.0,
        [valid_stop_order(stopPrice=stop_price)],
    )

    assert result.status == "UNKNOWN"
    assert result.approved is False

def test_wrong_side_is_not_approved(verifier):
    result = verifier.verify(
        "AAPL_US_EQ",
        0.1,
        200.0,
        [valid_stop_order(side="BUY")],
    )

    assert result.status == "UNKNOWN"
    assert result.approved is False