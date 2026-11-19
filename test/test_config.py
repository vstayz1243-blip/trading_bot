from dataclasses import FrozenInstanceError

import pytest

from config.risk_limits import RISK_LIMITS, RiskLimits
from config.settings import SETTINGS, RuntimeSettings


def test_default_risk_limits_preserve_existing_values():
    assert RISK_LIMITS.min_confidence == 0.65
    assert RISK_LIMITS.max_order_value == 500.0
    assert RISK_LIMITS.max_position_value == 1000.0
    assert RISK_LIMITS.quantity_precision == 6


def test_risk_limits_are_immutable():
    with pytest.raises(FrozenInstanceError):
        RISK_LIMITS.max_order_value = 1000.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_confidence": -0.1},
        {"min_confidence": 1.1},
        {"max_order_value": 0},
        {"max_order_value": float("inf")},
        {"max_position_value": -1},
        {"quantity_precision": -1},
        {"quantity_precision": True},
    ],
)
def test_invalid_risk_limits_are_rejected(kwargs):
    with pytest.raises(ValueError):
        RiskLimits(**kwargs)


def test_execution_settings_keep_safe_defaults():
    assert SETTINGS.dry_run is True
    assert SETTINGS.demo_orders_enabled is False


def test_runtime_settings_are_immutable():
    with pytest.raises(FrozenInstanceError):
        SETTINGS.dry_run = False


def test_runtime_settings_reject_live_execution():
    with pytest.raises(ValueError, match="dry_run"):
        RuntimeSettings(dry_run=False)


def test_runtime_settings_reject_demo_orders():
    with pytest.raises(ValueError, match="demo_orders_enabled"):
        RuntimeSettings(demo_orders_enabled=True)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"ollama_base_url": ""},
        {"ollama_model": ""},
        {"ollama_timeout": 0},
        {"ollama_timeout": float("nan")},
        {"ollama_max_concurrent": 0},
        {"ollama_max_concurrent": True},
    ],
)
def test_invalid_runtime_settings_are_rejected(kwargs):
    with pytest.raises(ValueError):
        RuntimeSettings(**kwargs)
