from dataclasses import dataclass, field
from typing import Any


@dataclass
class Position:
    ticker: str
    quantity: float
    average_price: float
    current_price: float
    profit_loss: float
    profit_loss_percentage: float
    currency: str = "UNKNOWN"


@dataclass
class MarketData:
    ticker: str
    current_price: float
    currency: str = "UNKNOWN"
    fx_rate_to_account: float | None = None

    change_24h: float | None = None
    volume: float | None = None

    positions: list[Position] = field(default_factory=list)

    account_cash: float | None = None
    account_equity: float | None = None
    account_currency: str = "UNKNOWN"

    technical_indicators: dict[str, Any] = field(default_factory=dict)
    portfolio_metrics: dict[str, Any] = field(default_factory=dict)
    historical_data_points: int = 0

    def __post_init__(self) -> None:
        if self.current_price < 0:
            raise ValueError("current_price darf nicht negativ sein.")

        if self.account_cash is not None and self.account_cash < 0:
            raise ValueError("account_cash darf nicht negativ sein.")

        if self.account_equity is not None and self.account_equity < 0:
            raise ValueError("account_equity darf nicht negativ sein.")

        if self.fx_rate_to_account is not None:
            if self.fx_rate_to_account <= 0:
                raise ValueError(
                    "fx_rate_to_account muss größer als 0 sein."
                )

        if self.historical_data_points < 0:
            raise ValueError(
                "historical_data_points darf nicht negativ sein."
            )