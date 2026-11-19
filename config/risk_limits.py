import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RiskLimits:
    """Central deterministic trading limits."""

    min_confidence: float = 0.65
    max_order_value: float = 500.0
    max_position_value: float = 1000.0
    quantity_precision: int = 6

    def __post_init__(self) -> None:
        for name, value in (
            ("min_confidence", self.min_confidence),
            ("max_order_value", self.max_order_value),
            ("max_position_value", self.max_position_value),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(f"{name} must be a finite number.")

        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1.")
        if self.max_order_value <= 0:
            raise ValueError("max_order_value must be positive.")
        if self.max_position_value <= 0:
            raise ValueError("max_position_value must be positive.")
        if (
            isinstance(self.quantity_precision, bool)
            or not isinstance(self.quantity_precision, int)
            or self.quantity_precision < 0
        ):
            raise ValueError("quantity_precision must be a non-negative integer.")


RISK_LIMITS = RiskLimits()
