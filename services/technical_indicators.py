
from typing import Any

import pandas as pd


def calculate_technical_indicators(
    history: pd.DataFrame,
) -> dict[str, Any]:
    """
    Berechnet technische Indikatoren aus historischen Tages- oder
    Intraday-Kerzen mit den Spalten High, Low und Close.

    RSI und ATR werden erst bei ausreichender Datenbasis ausgegeben.
    """
    required_columns = {"High", "Low", "Close"}

    if history is None or history.empty:
        raise ValueError("Historische Kursdaten fehlen.")

    if not required_columns.issubset(history.columns):
        missing = required_columns - set(history.columns)
        raise ValueError(
            f"Fehlende OHLC-Spalten: {sorted(missing)}"
        )

    data = history.copy()

    for column in required_columns:
        data[column] = pd.to_numeric(
            data[column], errors="coerce"
        )

    data = data.dropna(subset=["High", "Low", "Close"])

    if data.empty:
        raise ValueError("Keine gültigen OHLC-Daten vorhanden.")

    if (data["Close"] <= 0).any():
        raise ValueError("Historische Schlusskurse müssen positiv sein.")

    close = data["Close"]
    high = data["High"]
    low = data["Low"]

    # Gleitende Durchschnitte
    sma20 = close.rolling(window=20, min_periods=20).mean()
    sma50 = close.rolling(window=50, min_periods=50).mean()
    ema20 = close.ewm(span=20, adjust=False, min_periods=20).mean()

    # RSI nach der üblichen Wilder-Glättung
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)

    average_gain = gains.ewm(
        alpha=1 / 14, min_periods=14, adjust=False
    ).mean()

    average_loss = losses.ewm(
        alpha=1 / 14, min_periods=14, adjust=False
    ).mean()

    relative_strength = average_gain / average_loss
    rsi = 100 - (100 / (1 + relative_strength))

    # Sonderfälle: nur steigende oder nur fallende Kurse
    rsi = rsi.mask(
        (average_loss == 0) & (average_gain > 0), 100.0
    )
    rsi = rsi.mask(
        (average_loss == 0) & (average_gain == 0), 50.0
    )

    # Average True Range (ATR)
    previous_close = close.shift(1)

    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr14 = true_range.ewm(
        alpha=1 / 14, min_periods=14, adjust=False
    ).mean()

    def latest(series: pd.Series) -> float | None:
        value = series.iloc[-1]
        if pd.isna(value):
            return None
        return float(value)

    current_close = float(close.iloc[-1])
    latest_sma20 = latest(sma20)
    latest_sma50 = latest(sma50)
    latest_ema20 = latest(ema20)

    trend = "UNKNOWN"

    if latest_sma20 is not None and latest_sma50 is not None:
        if latest_sma20 > latest_sma50:
            trend = "BULLISH"
        elif latest_sma20 < latest_sma50:
            trend = "BEARISH"
        else:
            trend = "NEUTRAL"

    return {
        "data_points": len(data),
        "latest_close": current_close,
        "sma20": latest_sma20,
        "sma50": latest_sma50,
        "ema20": latest_ema20,
        "rsi14": latest(rsi),
        "atr14": latest(atr14),
        "trend": trend,
        "data_sufficient": (
            len(data) >= 50
            and latest(rsi) is not None
            and latest(atr14) is not None
        ),
    }
