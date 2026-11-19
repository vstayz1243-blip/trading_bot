
import math
from unittest.mock import Mock

import pytest

from strategy.decision import Action, TradingDecision
from strategy.risk_manager import RiskManager
from execution.order_executor import (
    DEMO_BASE_URL,
    OrderExecutor,
    OrderExecutionError,
)


def make_decision(
    action: Action = Action.BUY,
    quantity: float = 2.0,
    ticker: str = "AAPL_US_EQ",
) -> TradingDecision:
    return TradingDecision(
        ticker=ticker,
        action=action,
        confidence=0.9,
        reason="Testentscheidung",
        current_price=100.0,
        quantity=quantity,
    )


# --------------------------------------------------
# RiskManager
# --------------------------------------------------

def test_risk_manager_accepts_valid_buy():
    manager = RiskManager(
        max_order_value=500.0,
        max_position_value=1000.0,
    )

    approved, reason = manager.validate(
        decision=make_decision(Action.BUY, 2.0),
        current_price_account_currency=100.0,
        current_position_value=0.0,
        current_position_quantity=0.0,
        available_cash=500.0,
        order_quantity=2.0,
    )

    assert approved is True
    assert "BUY" in reason


def test_risk_manager_rejects_order_above_limit():
    manager = RiskManager(max_order_value=500.0)

    approved, reason = manager.validate(
        decision=make_decision(Action.BUY, 6.0),
        current_price_account_currency=100.0,
        current_position_value=0.0,
        current_position_quantity=0.0,
        available_cash=1000.0,
        order_quantity=6.0,
    )

    assert approved is False
    assert "überschreitet" in reason


def test_risk_manager_rejects_sell_above_position():
    manager = RiskManager()

    approved, reason = manager.validate(
        decision=make_decision(Action.SELL, 3.0),
        current_price_account_currency=100.0,
        current_position_value=200.0,
        current_position_quantity=2.0,
        available_cash=500.0,
        order_quantity=3.0,
    )

    assert approved is False
    assert "Bestand" in reason


def test_risk_manager_rejects_insufficient_cash():
    manager = RiskManager()

    approved, reason = manager.validate(
        decision=make_decision(Action.BUY, 2.0),
        current_price_account_currency=100.0,
        current_position_value=0.0,
        current_position_quantity=0.0,
        available_cash=100.0,
        order_quantity=2.0,
    )

    assert approved is False
    assert "Guthaben" in reason


def test_risk_manager_rejects_position_limit():
    manager = RiskManager(
        max_order_value=500.0,
        max_position_value=300.0,
    )

    approved, reason = manager.validate(
        decision=make_decision(Action.BUY, 2.0),
        current_price_account_currency=100.0,
        current_position_value=250.0,
        current_position_quantity=2.5,
        available_cash=500.0,
        order_quantity=2.0,
    )

    assert approved is False
    assert "Positionswert" in reason


# --------------------------------------------------
# OrderExecutor: Dry-Run und Aktionen
# --------------------------------------------------

def test_dry_run_never_submits_order():
    trading212 = Mock()
    executor = OrderExecutor(trading212, dry_run=True)

    result = executor.execute(make_decision(Action.BUY, 2.0))

    assert result["dry_run"] is True
    assert result["status"] == "NOT_SUBMITTED"
    assert result["ticker"] == "AAPL_US_EQ"
    assert result["action"] == "BUY"
    assert result["quantity"] == 2.0

    trading212.place_market_order.assert_not_called()


def test_hold_never_submits_order():
    trading212 = Mock()
    executor = OrderExecutor(trading212, dry_run=True)

    result = executor.execute(make_decision(Action.HOLD, 0.0))

    assert result is None
    trading212.place_market_order.assert_not_called()

def test_sell_order_uses_negative_quantity(tmp_path):
    trading212 = Mock()
    trading212.base_url = DEMO_BASE_URL
    trading212.demo_orders_enabled = True

    # Vor dem Verkauf sind 2 AAPL-Aktien vorhanden.
    # Nach dem Verkauf muss die Position leer sein.
    trading212.get_positions.side_effect = [
        [
            {
                "ticker": "AAPL_US_EQ",
                "quantity": 2.0,
                "averagePrice": 340.0,
                "currentPrice": 345.0,
            }
        ],
        [],
        [],
    ]

    trading212.get_pending_orders.return_value = []
    trading212.place_market_order.return_value = {"status": "mocked"}

    executor = OrderExecutor(
        trading212,
        dry_run=False,
        state_path=tmp_path / "order_execution_state.json",
    )

    # Stop-Loss-Erstellung isolieren.
    executor._place_and_verify_stop = Mock(
        return_value={"status": "verified"}
    )

    result = executor.execute(make_decision(Action.SELL, 2.0))

    trading212.place_market_order.assert_called_once()

    call_kwargs = trading212.place_market_order.call_args.kwargs
    assert call_kwargs["quantity"] == -2.0


def test_buy_order_uses_positive_quantity(tmp_path):
    trading212 = Mock()
    trading212.base_url = DEMO_BASE_URL
    trading212.demo_orders_enabled = True

    # Vor dem Kauf: keine Position.
    # Nach dem Kauf: Position ist sichtbar.
    trading212.get_positions.side_effect = [
        [],
        [
            {
                "ticker": "AAPL_US_EQ",
                "quantity": 2.0,
                "averagePrice": 100.0,
                "currentPrice": 100.0,
            }
        ],
    ]

    trading212.get_pending_orders.return_value = []
    trading212.place_market_order.return_value = {"status": "mocked"}

    executor = OrderExecutor(trading212, dry_run=False, state_path=tmp_path / "order_execution_state.json")

    # Stop-Loss-Logik wird separat getestet.
    executor._place_and_verify_stop = Mock(
        return_value={"status": "verified"}
    )

    result = executor.execute(make_decision(Action.BUY, 2.0))

    trading212.place_market_order.assert_called_once_with(
        ticker="AAPL_US_EQ",
        quantity=2.0,
    )
    executor._place_and_verify_stop.assert_called_once()

    assert result["status"] == "EXECUTED_AND_PROTECTED"
    assert result["order"] == {"status": "mocked"}
    assert result["action"] == "BUY"


# --------------------------------------------------
# OrderExecutor: Ungültige Mengen
# --------------------------------------------------

@pytest.mark.parametrize(
    "quantity",
    [
        0,
        -1,
        math.nan,
        math.inf,
        -math.inf,
        True,
    ],
)
def test_executor_rejects_invalid_quantities(quantity):
    trading212 = Mock()
    executor = OrderExecutor(trading212, dry_run=False)

    if (
        isinstance(quantity, bool)
        or not isinstance(quantity, (int, float))
        or not math.isfinite(quantity)
        or quantity < 0
    ):
        with pytest.raises(ValueError):
            make_decision(Action.BUY, quantity)
    else:
        decision = make_decision(Action.BUY, quantity)
        with pytest.raises(ValueError, match="Ordermenge"):
            executor.execute(decision)

    trading212.place_market_order.assert_not_called()


# --------------------------------------------------
# OrderExecutor: Ungültige Ticker
# --------------------------------------------------

@pytest.mark.parametrize("ticker", ["", " ", "\t"])
def test_executor_rejects_empty_ticker(ticker):
    trading212 = Mock()
    executor = OrderExecutor(trading212, dry_run=False)

    with pytest.raises(ValueError, match="Ticker"):
        executor.execute(
            make_decision(
                Action.BUY,
                1.0,
                ticker=ticker,
            )
        )

    trading212.place_market_order.assert_not_called()


# --------------------------------------------------
# OrderExecutor: Konfiguration und unbekannte Aktion
# --------------------------------------------------

def test_executor_rejects_non_boolean_dry_run():
    trading212 = Mock()

    with pytest.raises(TypeError, match="dry_run"):
        OrderExecutor(trading212, dry_run=1)

    trading212.place_market_order.assert_not_called()


def test_executor_rejects_unknown_action():
    trading212 = Mock()

    with pytest.raises(ValueError, match="Ungültige Handelsaktion"):
        TradingDecision(
            ticker="AAPL_US_EQ",
            action="INVALID",
            confidence=0.9,
            reason="Testentscheidung",
            current_price=100.0,
            quantity=1.0,
        )

    trading212.place_market_order.assert_not_called()


def test_buy_order_is_not_retried_when_position_is_not_visible(tmp_path):
    trading212 = Mock()
    trading212.base_url = DEMO_BASE_URL
    trading212.demo_orders_enabled = True

    # Erste Abfrage: keine bestehende Position.
    # Zweite Abfrage: Position nach dem Kauf nicht sichtbar.
    trading212.get_positions.side_effect = [[], []]
    trading212.get_pending_orders.return_value = []
    trading212.place_market_order.return_value = {"status": "mocked"}

    executor = OrderExecutor(
        trading212,
        dry_run=False,
        position_wait_attempts=1,
        position_wait_interval=0,
        state_path= tmp_path / "order_execution_state.json"
    )

    with pytest.raises(OrderExecutionError):
        executor.execute(make_decision(Action.BUY, 2.0))

    trading212.place_market_order.assert_called_once_with(
        ticker="AAPL_US_EQ",
        quantity=2.0,
    )

def test_persistent_lock_blocks_orders_after_restart(tmp_path):
    from execution.order_executor import OrderExecutionError

    client = Mock()
    client.base_url = DEMO_BASE_URL
    client.demo_orders_enabled = True

    state_path = tmp_path / "order_execution_state.json"

    first_executor = OrderExecutor(
        trading212=client,
        dry_run=False,
        state_path=state_path,
    )

    first_executor._mark_pending(
        action="BUY",
        ticker="AAPL_US_EQ",
        quantity=2.0,
        stage="SUBMITTING_MARKET_ORDER",
    )

    # Simuliert einen Neustart: neuer Executor, dieselbe Statusdatei.
    restarted_executor = OrderExecutor(
        trading212=client,
        dry_run=False,
        state_path=state_path,
    )

    with pytest.raises(OrderExecutionError, match="gesperrt"):
        restarted_executor.execute(make_decision(Action.BUY))

    client.place_market_order.assert_not_called()


def test_market_order_timeout_persists_lock_and_prevents_retry(tmp_path):
    import json

    client = Mock()
    client.base_url = DEMO_BASE_URL
    client.demo_orders_enabled = True
    client.get_positions.return_value = []
    client.get_pending_orders.return_value = []
    client.place_market_order.side_effect = TimeoutError(
        "Simulierter API-Timeout"
    )

    state_path = tmp_path / "order_execution_state.json"

    executor = OrderExecutor(
        trading212=client,
        dry_run=False,
        state_path=state_path,
    )

    # Der Timeout kann bedeuten, dass Trading 212 die Order bereits
    # angenommen hat. Deshalb darf sie nicht automatisch wiederholt werden.
    with pytest.raises(TimeoutError):
        executor.execute(make_decision(Action.BUY))

    assert state_path.exists()

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == "PENDING_RECONCILIATION"
    assert state["action"] == "BUY"
    assert state["ticker"] == "AAPL_US_EQ"
    assert state["stage"] == "SUBMITTING_MARKET_ORDER"

    # Auch ein erneuter Aufruf muss blockiert werden.
    with pytest.raises(OrderExecutionError, match="gesperrt"):
        executor.execute(make_decision(Action.BUY))

    client.place_market_order.assert_called_once_with(
        ticker="AAPL_US_EQ",
        quantity=2.0,
    )


def test_stop_loss_failure_persists_lock(tmp_path):
    import json

    client = Mock()
    client.base_url = DEMO_BASE_URL
    client.demo_orders_enabled = True

    client.get_positions.side_effect = [
        [],
        [
            {
                "ticker": "AAPL_US_EQ",
                "quantity": 2.0,
                "averagePrice": 100.0,
                "currentPrice": 100.0,
            }
        ],
    ]
    client.get_pending_orders.return_value = []
    client.place_market_order.return_value = {"id": 123}
    client.place_stop_order.side_effect = TimeoutError(
        "Simulierter Stop-Loss-Timeout"
    )

    state_path = tmp_path / "order_execution_state.json"

    executor = OrderExecutor(
        trading212=client,
        dry_run=False,
        state_path=state_path,
    )

    # Der Kauf kann bereits ausgeführt sein. Wenn der Stop-Loss fehlschlägt,
    # muss die Sperre bestehen bleiben.
    with pytest.raises(TimeoutError):
        executor.execute(make_decision(Action.BUY))

    assert state_path.exists()

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == "PENDING_RECONCILIATION"
    assert state["action"] == "BUY"
    assert state["stage"] == "SUBMITTING_STOP_LOSS"

    client.place_market_order.assert_called_once()
    client.place_stop_order.assert_called_once()


def test_find_position_supports_nested_instrument_ticker():
    client = Mock()
    executor = OrderExecutor(client, dry_run=True)

    position = {
        "instrument": {"ticker": "AAPL_US_EQ"},
        "quantity": 0.2,
    }

    result = executor._find_position(
        "AAPL_US_EQ",
        [position],
    )

    assert result is position


def test_find_position_rejects_duplicate_nested_tickers():
    client = Mock()
    executor = OrderExecutor(client, dry_run=True)

    positions = [
        {"instrument": {"ticker": "AAPL_US_EQ"}, "quantity": 0.1},
        {"instrument": {"ticker": "AAPL_US_EQ"}, "quantity": 0.2},
    ]

    with pytest.raises(OrderExecutionError, match="Mehrere Positionseinträge"):
        executor._find_position("AAPL_US_EQ", positions)


def test_active_stops_supports_nested_instrument_ticker():
    client = Mock()
    executor = OrderExecutor(client, dry_run=True)

    order = {
        "instrument": {"ticker": "AAPL_US_EQ"},
        "status": "NEW",
        "type": "STOP",
    }

    result = executor._active_stops("AAPL_US_EQ", [order])

    assert result == [order]


# --------------------------------------------------
# Stop-Loss-Order-ID-Verifikation
# --------------------------------------------------

def make_stop_test_executor():
    client = Mock()
    client.base_url = DEMO_BASE_URL
    client.demo_orders_enabled = True

    executor = OrderExecutor(
        trading212=client,
        dry_run=False,
        position_wait_interval=0,
    )

    # Verhindert Schreibzugriffe auf den persistenten Ausführungsstatus.
    executor._update_pending_stage = Mock()

    position = {
        "ticker": "AAPL_US_EQ",
        "quantity": 2.0,
        "averagePrice": 100.0,
        "currentPrice": 110.0,
    }

    created_order = {
        "id": 123,
    }

    active_stop = {
        "id": 123,
        "ticker": "AAPL_US_EQ",
        "type": "STOP",
        "status": "CONFIRMED",
        "quantity": -2.0,
        "filledQuantity": 0.0,
        "stopPrice": 95.0,
        "side": "SELL",
    }

    client.get_pending_orders.side_effect = [
        [],
        [active_stop],
    ]
    client.place_stop_order.return_value = created_order

    return executor, client, position, created_order, active_stop


def test_stop_loss_accepts_matching_order_id():
    executor, client, position, _, active_stop = (
        make_stop_test_executor()
    )

    result = executor._place_and_verify_stop(
        "AAPL_US_EQ",
        position,
    )

    assert result["status"] == "VERIFIED"
    assert result["order"]["id"] == 123
    client.place_stop_order.assert_called_once_with(
        ticker="AAPL_US_EQ",
        quantity=-2.0,
        stop_price=95.0,
        time_validity="GOOD_TILL_CANCEL",
    )


def test_stop_loss_rejects_missing_created_order_id():
    executor, client, position, _, _ = make_stop_test_executor()
    client.place_stop_order.return_value = {}

    with pytest.raises(OrderExecutionError, match="keine gültige ID"):
        executor._place_and_verify_stop(
            "AAPL_US_EQ",
            position,
        )

    # Nach unklarer API-Antwort keine weitere Order senden.
    client.get_pending_orders.assert_called_once()


def test_stop_loss_rejects_mismatching_order_id():
    executor, client, position, _, active_stop = (
        make_stop_test_executor()
    )

    active_stop["id"] = 456

    with pytest.raises(OrderExecutionError, match="Order-ID"):
        executor._place_and_verify_stop(
            "AAPL_US_EQ",
            position,
        )


def test_stop_loss_rejects_missing_active_stop():
    executor, client, position, _, _ = make_stop_test_executor()
    client.get_pending_orders.side_effect = [
        [],
        [],
    ]

    with pytest.raises(OrderExecutionError, match="nicht eindeutig"):
        executor._place_and_verify_stop(
            "AAPL_US_EQ",
            position,
        )


def test_stop_loss_rejects_multiple_active_stops():
    executor, client, position, _, active_stop = (
        make_stop_test_executor()
    )

    second_stop = {
        **active_stop,
        "id": 456,
    }

    client.get_pending_orders.side_effect = [
        [],
        [active_stop, second_stop],
    ]

    with pytest.raises(OrderExecutionError, match="nicht eindeutig"):
        executor._place_and_verify_stop(
            "AAPL_US_EQ",
            position,
        )


# --------------------------------------------------
# OrderExecutor: Reconciliation nach unbekanntem Status
# --------------------------------------------------

def make_reconciliation_executor(tmp_path, action="BUY", stage="SUBMITTING_MARKET_ORDER"):
    client = Mock()
    client.base_url = DEMO_BASE_URL
    client.demo_orders_enabled = True
    client.get_positions.return_value = []
    client.get_pending_orders.return_value = []

    executor = OrderExecutor(
        trading212=client,
        dry_run=False,
        state_path=tmp_path / "order_execution_state.json",
    )

    executor._mark_pending(
        action=action,
        ticker="AAPL_US_EQ",
        quantity=2.0,
        stage=stage,
    )

    return executor, client


def test_reconciliation_without_pending_execution(tmp_path):
    client = Mock()
    executor = OrderExecutor(
        trading212=client,
        dry_run=False,
        state_path=tmp_path / "missing_state.json",
    )

    result = executor.reconcile_pending_execution()

    assert result["status"] == "NO_PENDING_EXECUTION"
    assert result["execution_blocked"] is False
    client.get_positions.assert_not_called()
    client.get_pending_orders.assert_not_called()


def test_reconciliation_keeps_lock_when_no_evidence_exists(tmp_path):
    executor, client = make_reconciliation_executor(tmp_path)

    result = executor.reconcile_pending_execution()

    assert result["status"] == "NO_CONCLUSIVE_EVIDENCE"
    assert result["execution_blocked"] is True

    # Die Sperre darf durch eine Diagnose nicht verschwinden.
    assert executor._read_execution_state() is not None

    # Es dürfen keine neuen Orders gesendet werden.
    client.place_market_order.assert_not_called()
    client.place_stop_order.assert_not_called()


def test_reconciliation_detects_existing_buy_position(tmp_path):
    executor, client = make_reconciliation_executor(tmp_path)

    client.get_positions.return_value = [
        {
            "ticker": "AAPL_US_EQ",
            "quantity": 2.0,
            "averagePrice": 100.0,
            "currentPrice": 100.0,
        }
    ]

    result = executor.reconcile_pending_execution()

    assert result["status"] == "BUY_POSITION_EXISTS_MANUAL_REVIEW"
    assert result["execution_blocked"] is True
    assert executor._read_execution_state() is not None


def test_reconciliation_blocks_when_matching_orders_are_unresolved(tmp_path):
    executor, client = make_reconciliation_executor(tmp_path)

    client.get_pending_orders.return_value = [
        {
            "ticker": "AAPL_US_EQ",
            "status": "NEW",
            "type": "MARKET",
            "quantity": 2.0,
        }
    ]

    result = executor.reconcile_pending_execution()

    assert result["status"] == "UNRESOLVED_ORDERS"
    assert result["execution_blocked"] is True
    assert executor._read_execution_state() is not None


def test_reconciliation_sell_requires_manual_review(tmp_path):
    executor, client = make_reconciliation_executor(
        tmp_path,
        action="SELL",
    )

    client.get_positions.return_value = [
        {
            "ticker": "AAPL_US_EQ",
            "quantity": 2.0,
            "averagePrice": 100.0,
            "currentPrice": 100.0,
        }
    ]

    result = executor.reconcile_pending_execution()

    assert result["status"] == "SELL_REQUIRES_MANUAL_REVIEW"
    assert result["execution_blocked"] is True
    assert executor._read_execution_state() is not None


def test_reconciliation_does_not_classify_active_stop_as_market_order(
    tmp_path,
):
    executor, client = make_reconciliation_executor(tmp_path)

    active_stop = {
        "id": 123,
        "ticker": "AAPL_US_EQ",
        "status": "CONFIRMED",
        "type": "STOP",
        "quantity": -2.0,
        "filledQuantity": 0.0,
        "stopPrice": 95.0,
        "side": "SELL",
    }

    client.get_pending_orders.return_value = [active_stop]

    result = executor.reconcile_pending_execution()

    assert result["status"] != "UNRESOLVED_ORDERS"
    assert result["execution_blocked"] is True
    assert executor._read_execution_state() is not None

    client.place_market_order.assert_not_called()
    client.place_stop_order.assert_not_called()