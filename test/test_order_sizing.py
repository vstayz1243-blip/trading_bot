from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from services.order_sizing import OrderSizingService
from strategy.decision import Action, TradingDecision
from strategy.risk_manager import RiskManager


@pytest.fixture
def service():
    return OrderSizingService()


@pytest.fixture
def risk_manager():
    return RiskManager(max_order_value=500.0, max_position_value=1000.0)


def make_decision(action=Action.BUY):
    return TradingDecision(
        ticker="AAPL_US_EQ",
        action=action,
        confidence=0.9,
        reason="Testentscheidung",
        current_price=10.0,
    )


def make_market_data(
    *,
    price=10.0,
    fx_rate=1.0,
    cash=100.0,
    positions=None,
):
    return SimpleNamespace(
        current_price=price,
        fx_rate_to_account=fx_rate,
        account_cash=cash,
        positions=[] if positions is None else positions,
    )


def test_buy_sizes_order_to_available_cash(service, risk_manager):
    decision, message = service.prepare_order(
        make_decision(Action.BUY),
        make_market_data(cash=100.0),
        risk_manager,
    )

    assert decision is not None
    assert decision.quantity == 10.0
    assert "BUY" in message


def test_buy_respects_max_order_value(service, risk_manager):
    decision, _ = service.prepare_order(
        make_decision(Action.BUY),
        make_market_data(cash=1000.0),
        risk_manager,
    )

    assert decision is not None
    assert decision.quantity == 50.0


def test_sell_uses_existing_position_quantity(service, risk_manager):
    position = SimpleNamespace(
        ticker="AAPL_US_EQ",
        quantity=2.5,
        current_price=10.0,
    )

    decision, _ = service.prepare_order(
        make_decision(Action.SELL),
        make_market_data(positions=[position]),
        risk_manager,
    )

    assert decision is not None
    assert decision.quantity == 2.5


def test_hold_does_not_call_risk_manager(service):
    manager = Mock()

    decision, message = service.prepare_order(
        make_decision(Action.HOLD),
        make_market_data(),
        manager,
    )

    assert decision is None
    assert message.startswith("HOLD")
    manager.validate.assert_not_called()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("price", float("nan")),
        ("price", float("inf")),
        ("fx_rate", 0.0),
        ("cash", -1.0),
        ("cash", True),
    ],
)
def test_rejects_invalid_market_values(
    service,
    risk_manager,
    field,
    value,
):
    decision, message = service.prepare_order(
        make_decision(),
        make_market_data(**{field: value}),
        risk_manager,
    )

    assert decision is None
    assert message


def test_rejects_missing_positions(service, risk_manager):
    market_data = make_market_data()
    market_data.positions = None

    decision, message = service.prepare_order(
        make_decision(),
        market_data,
        risk_manager,
    )

    assert decision is None
    assert "Positionsdaten" in message


def test_rejects_duplicate_matching_positions(service, risk_manager):
    position = SimpleNamespace(
        ticker="AAPL_US_EQ",
        quantity=1.0,
        current_price=10.0,
    )

    decision, message = service.prepare_order(
        make_decision(),
        make_market_data(positions=[position, position]),
        risk_manager,
    )

    assert decision is None
    assert "Mehrere passende Positionen" in message


def test_sell_without_position_is_rejected(service, risk_manager):
    decision, message = service.prepare_order(
        make_decision(Action.SELL),
        make_market_data(),
        risk_manager,
    )

    assert decision is None
    assert "Keine bestehende Position" in message


def test_risk_manager_rejection_is_authoritative(service):
    manager = Mock()
    manager.validate.return_value = (False, "Risikolimit verletzt")

    decision, message = service.prepare_order(
        make_decision(),
        make_market_data(),
        manager,
    )

    assert decision is None
    assert message == "Risikolimit verletzt"
    manager.validate.assert_called_once()


@pytest.mark.parametrize(
    ("max_order_value", "precision"),
    [
        (0, 6),
        (-1, 6),
        (float("inf"), 6),
        (True, 6),
        (500.0, -1),
        (500.0, True),
    ],
)
def test_rejects_invalid_configuration(max_order_value, precision):
    with pytest.raises(ValueError):
        OrderSizingService(
            max_order_value=max_order_value,
            quantity_precision=precision,
        )
