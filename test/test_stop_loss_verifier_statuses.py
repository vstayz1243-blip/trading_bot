
import pytest

from services.stop_loss_verifier import StopLossVerifier


@pytest.fixture
def verifier():
    return StopLossVerifier()


def make_stop_order(status="NEW", ticker="AAPL_US_EQ"):
    return {
        "ticker": ticker,
        "type": "STOP",
        "status": status,
        "side": "SELL",
        "quantity": 0.2,
        "filledQuantity": 0,
        "stopPrice": 300.0,
    }


def test_unknown_stop_status_returns_unknown(verifier):
    result = verifier.verify(
        ticker="AAPL_US_EQ",
        position_quantity=0.2,
        current_price=340.0,
        orders=[make_stop_order(status="PENDING_REVIEW")],
    )

    assert result.status == "UNKNOWN"
    assert result.approved is False


@pytest.mark.parametrize(
    "status",
    ["CANCELLED", "FILLED", "REJECTED", "EXPIRED"],
)
def test_terminal_stop_status_is_not_approved(verifier, status):
    result = verifier.verify(
        ticker="AAPL_US_EQ",
        position_quantity=0.2,
        current_price=340.0,
        orders=[make_stop_order(status=status)],
    )

    assert result.status == "MISSING"
    assert result.approved is False


@pytest.mark.parametrize("status", ["NEW", "CONFIRMED"])
def test_confirmed_stop_order_is_approved(verifier, status):
    result = verifier.verify(
        ticker="AAPL_US_EQ",
        position_quantity=0.2,
        current_price=340.0,
        orders=[make_stop_order(status=status)],
    )

    assert result.status == "VERIFIED"
    assert result.approved is True


def test_unknown_stop_status_blocks_otherwise_valid_stop(verifier):
    orders = [
        make_stop_order(status="NEW"),
        make_stop_order(status="UNRECOGNIZED"),
    ]

    result = verifier.verify(
        ticker="AAPL_US_EQ",
        position_quantity=0.2,
        current_price=340.0,
        orders=orders,
    )

    assert result.status == "UNKNOWN"
    assert result.approved is False


def test_unknown_status_for_other_ticker_is_irrelevant(verifier):
    result = verifier.verify(
        ticker="AAPL_US_EQ",
        position_quantity=0.2,
        current_price=340.0,
        orders=[
            make_stop_order(status="NEW"),
            make_stop_order(
                status="UNRECOGNIZED",
                ticker="MSFT_US_EQ",
            ),
        ],
    )

    assert result.status == "VERIFIED"
    assert result.approved is True


def test_missing_status_returns_unknown(verifier):
    order = make_stop_order()
    del order["status"]

    result = verifier.verify(
        ticker="AAPL_US_EQ",
        position_quantity=0.2,
        current_price=340.0,
        orders=[order],
    )

    assert result.status == "UNKNOWN"
    assert result.approved is False
