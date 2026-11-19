
import logging

import yfinance as yf

from client.positions import PositionsClient
from models.market_data import MarketData, Position
from services.technical_indicators import calculate_technical_indicators
from services.portfolio_metrics import calculate_portfolio_metrics


logger = logging.getLogger(__name__)

YAHOO_TICKERS = {
    "AAPL_US_EQ": "AAPL",
}


class MarketDataService:
    def __init__(self, trading212):
        self.trading212 = trading212
        self.positions_client = PositionsClient(trading212)
        self._instrument_currencies = None

    def _get_instrument_currencies(self) -> dict[str, str]:
        if self._instrument_currencies is not None:
            return self._instrument_currencies

        instruments = self.trading212.get_instruments()
        currencies = {}

        for instrument in instruments or []:
            ticker = instrument.get("ticker")
            currency = instrument.get("currencyCode")

            if ticker and currency:
                currencies[ticker] = currency.upper()

        self._instrument_currencies = currencies
        return currencies

    def _get_fx_rate_to_account(
        self,
        source_currency: str,
        account_currency: str,
    ) -> float | None:
        """
        Liefert den Wechselkurs von der Instrumentwährung
        zur Kontowährung.

        Beispiel:
        USD -> EUR: EURUSD=X liefert USD pro EUR.
        Der Kurs wird deshalb invertiert.
        """
        source = source_currency.upper()
        target = account_currency.upper()

        if source == target:
            return 1.0

        if source == "UNKNOWN" or target == "UNKNOWN":
            return None

        pair = f"{target}{source}=X"

        try:
            history = yf.Ticker(pair).history(
                period="5d",
                interval="1d",
            )

            if history.empty or "Close" not in history.columns:
                logger.warning(
                    "Kein FX-Kurs für %s -> %s verfügbar.",
                    source,
                    target,
                )
                return None

            closes = history["Close"].dropna()

            if closes.empty:
                logger.warning(
                    "Keine gültigen FX-Kurse für %s verfügbar.",
                    pair,
                )
                return None

            quote = float(closes.iloc[-1])

            if quote <= 0:
                logger.warning(
                    "Ungültiger FX-Kurs für %s: %s",
                    pair,
                    quote,
                )
                return None

            return 1.0 / quote

        except Exception:
            logger.exception(
                "FX-Kurs für %s -> %s konnte nicht geladen werden.",
                source,
                target,
            )
            return None

    def get_market_data(self, ticker: str) -> MarketData:
        yahoo_ticker = YAHOO_TICKERS.get(ticker)

        if yahoo_ticker is None:
            raise ValueError(
                f"Kein Yahoo-Ticker-Mapping für {ticker}"
            )

        logger.info(
            "Lade historische Kursdaten für %s.",
            yahoo_ticker,
        )

        stock = yf.Ticker(yahoo_ticker)

        daily = stock.history(
            period="3mo",
            interval="1d",
            auto_adjust=False,
        )

        if daily.empty:
            raise RuntimeError(
                f"Keine historischen Kursdaten für {yahoo_ticker}."
            )

        daily = daily.dropna(subset=["Close"])

        if daily.empty:
            raise RuntimeError(
                f"Keine gültigen Schlusskurse für {yahoo_ticker}."
            )

        intraday = stock.history(
            period="1d",
            interval="5m",
            auto_adjust=False,
        )

        intraday_closes = (
            intraday["Close"].dropna()
            if not intraday.empty
            else None
        )

        if (
            intraday_closes is not None
            and not intraday_closes.empty
        ):
            current_price = float(intraday_closes.iloc[-1])
        else:
            current_price = float(daily["Close"].iloc[-1])

        if current_price <= 0:
            raise RuntimeError(
                f"Ungültiger Kurs für {yahoo_ticker}: "
                f"{current_price}"
            )

        daily_closes = daily["Close"].dropna()

        if len(daily_closes) >= 2:
            previous_close = float(daily_closes.iloc[-2])
            change_24h = (
                current_price / previous_close - 1
            ) * 100
        else:
            change_24h = None

        volumes = daily["Volume"].dropna()
        volume = (
            float(volumes.iloc[-1])
            if not volumes.empty
            else None
        )

        technical_indicators = (
            calculate_technical_indicators(daily)
        )

        # Trading212-Kontodaten und Positionen laden.
        account = self.trading212.get_account_summary()
        raw_positions = self.positions_client.get_all() or []
        instrument_currencies = self._get_instrument_currencies()

        normalized_positions = []

        for item in raw_positions:
            instrument = item.get("instrument") or {}
            position_ticker = instrument.get(
                "ticker",
                "UNKNOWN",
            )

            currency = (
                instrument.get("currencyCode")
                or instrument_currencies.get(position_ticker)
                or "UNKNOWN"
            ).upper()

            quantity = float(item.get("quantity", 0) or 0)
            average_price = float(
                item.get("averagePricePaid", 0) or 0
            )
            position_price = float(
                item.get("currentPrice", 0) or 0
            )

            cost_basis = quantity * average_price
            position_value = quantity * position_price
            profit_loss = position_value - cost_basis

            profit_loss_percentage = (
                profit_loss / cost_basis * 100
                if cost_basis > 0
                else 0.0
            )

            normalized_positions.append(
                Position(
                    ticker=position_ticker,
                    quantity=quantity,
                    average_price=average_price,
                    current_price=position_price,
                    profit_loss=profit_loss,
                    profit_loss_percentage=profit_loss_percentage,
                    currency=currency,
                )
            )

        account_cash = float(
            account["cash"]["availableToTrade"]
        )
        account_equity = float(account["totalValue"])
        account_currency = str(
            account.get("currency", "UNKNOWN")
        ).upper()

        # Wechselkurse für vorhandene Positionen laden.
        fx_rates_to_account = {}

        for position in normalized_positions:
            currency = position.currency.upper()

            if currency == "UNKNOWN":
                continue

            if currency == account_currency:
                fx_rates_to_account[currency] = 1.0
                continue

            if currency not in fx_rates_to_account:
                rate = self._get_fx_rate_to_account(
                    source_currency=currency,
                    account_currency=account_currency,
                )

                if rate is not None:
                    fx_rates_to_account[currency] = rate

        portfolio_metrics = calculate_portfolio_metrics(
            positions=normalized_positions,
            account_cash=account_cash,
            account_equity=account_equity,
            account_currency=account_currency,
            fx_rates_to_account=fx_rates_to_account,
        )

        # Währung des Instruments bestimmen.
        target_currency = (
            instrument_currencies.get(ticker)
            or "UNKNOWN"
        ).upper()

        if target_currency == "UNKNOWN":
            try:
                yahoo_currency = stock.info.get("currency")

                if yahoo_currency:
                    target_currency = str(
                        yahoo_currency
                    ).upper()

            except Exception:
                logger.warning(
                    "Yahoo-Währung für %s konnte nicht "
                    "ermittelt werden.",
                    yahoo_ticker,
                )

        # Wechselkurs des Zielinstruments in die Kontowährung.
        fx_rate_to_account = None

        if (
            target_currency != "UNKNOWN"
            and account_currency != "UNKNOWN"
        ):
            fx_rate_to_account = self._get_fx_rate_to_account(
                source_currency=target_currency,
                account_currency=account_currency,
            )

        logger.info(
            "Portfolio: Kontowährung=%s, Eigenkapital=%.2f, "
            "verfügbares Guthaben=%.2f",
            account_currency,
            account_equity,
            account_cash,
        )

        logger.info(
            "Portfolio-Kennzahlen: %s",
            portfolio_metrics,
        )

        logger.info(
            "Instrument: %s | Kurs: %.4f %s | "
            "FX zur Kontowährung: %s",
            ticker,
            current_price,
            target_currency,
            fx_rate_to_account,
        )

        return MarketData(
            ticker=ticker,
            current_price=current_price,
            currency=target_currency,
            fx_rate_to_account=fx_rate_to_account,
            change_24h=change_24h,
            volume=volume,
            positions=normalized_positions,
            account_cash=account_cash,
            account_equity=account_equity,
            account_currency=account_currency,
            technical_indicators=technical_indicators,
            portfolio_metrics=portfolio_metrics,
            historical_data_points=len(daily),
        )
