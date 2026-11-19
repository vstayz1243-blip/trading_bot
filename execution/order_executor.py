import json
import logging
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.stop_loss_verifier import StopLossVerifier
from strategy.decision import Action, TradingDecision


logger = logging.getLogger(__name__)

DEMO_BASE_URL = "https://demo.trading212.com/api/v0"
STOP_LOSS_DISTANCE = 0.05
POSITION_QUANTITY_TOLERANCE = 1e-6

ACTIVE_ORDER_STATUSES = {"NEW", "CONFIRMED"}
STOP_ORDER_TYPES = {"STOP", "STOP_LIMIT"}

# Diese Statuswerte gelten als ungeklärt und blockieren neue Orders.
UNRESOLVED_ORDER_STATUSES = {
    "CANCELLING",
    "LOCAL",
    "UNCONFIRMED",
}


class OrderExecutionError(RuntimeError):
    """Orderausführung wurde aus Sicherheitsgründen abgebrochen."""


class OrderExecutor:
    def __init__(
        self,
        trading212: Any,
        dry_run: bool = True,
        stop_loss_distance: float = STOP_LOSS_DISTANCE,
        position_wait_attempts: int = 5,
        position_wait_interval: float = 1.0,
        state_path: str | Path = "data/order_execution_state.json",
    ) -> None:
        if not isinstance(dry_run, bool):
            raise TypeError("dry_run muss bool sein.")

        if (
            isinstance(stop_loss_distance, bool)
            or not isinstance(stop_loss_distance, (int, float))
            or not math.isfinite(stop_loss_distance)
            or not 0 < stop_loss_distance < 1
        ):
            raise ValueError(
                "stop_loss_distance muss zwischen 0 und 1 liegen."
            )

        if (
            isinstance(position_wait_attempts, bool)
            or not isinstance(position_wait_attempts, int)
            or position_wait_attempts < 1
        ):
            raise ValueError(
                "position_wait_attempts muss mindestens 1 sein."
            )

        if (
            isinstance(position_wait_interval, bool)
            or not isinstance(position_wait_interval, (int, float))
            or not math.isfinite(position_wait_interval)
            or position_wait_interval < 0
        ):
            raise ValueError(
                "position_wait_interval darf nicht negativ sein."
            )

        if not isinstance(state_path, (str, Path)):
            raise TypeError("state_path muss ein String oder Path sein.")

        if not str(state_path).strip():
            raise ValueError("state_path darf nicht leer sein.")

        self.trading212 = trading212
        self.dry_run = dry_run
        self.stop_loss_distance = float(stop_loss_distance)
        self.position_wait_attempts = position_wait_attempts
        self.position_wait_interval = float(position_wait_interval)
        self.state_path = Path(state_path)

    # ------------------------------------------------------------------
    # Einstiegspunkt
    # ------------------------------------------------------------------

    def execute(
        self,
        decision: TradingDecision,
    ) -> dict[str, Any] | None:
        if decision.action == Action.HOLD:
            logger.info("HOLD: Keine Order erforderlich.")
            return None

        if decision.action not in (Action.BUY, Action.SELL):
            raise ValueError(
                f"Unbekannte Handelsaktion: {decision.action}"
            )

        ticker = decision.ticker
        quantity = decision.quantity

        if not isinstance(ticker, str) or not ticker.strip():
            raise ValueError("Ticker darf nicht leer sein.")

        if (
            isinstance(quantity, bool)
            or not isinstance(quantity, (int, float))
            or not math.isfinite(quantity)
            or quantity <= 0
        ):
            raise ValueError(
                "Ordermenge muss positiv und endlich sein."
            )

        ticker = ticker.strip()
        quantity = float(quantity)

        if self.dry_run:
            logger.info(
                "[DRY-RUN] Keine Order gesendet: %s %.6f %s",
                decision.action.value,
                quantity,
                ticker,
            )
            return {
                "dry_run": True,
                "ticker": ticker,
                "action": decision.action.value,
                "quantity": quantity,
                "status": "NOT_SUBMITTED",
            }

        self._require_demo_execution()
        self._ensure_not_blocked()

        if decision.action == Action.BUY:
            result = self._execute_buy(ticker, quantity)
        else:
            result = self._execute_sell(ticker, quantity)

        # Die Sperre wird nur aufgehoben, wenn die komplette Ausführung
        # inklusive der erforderlichen Positions-/Stop-Prüfungen erfolgreich war.
        self._clear_pending()
        return result

    # ------------------------------------------------------------------
    # Persistenter Ausführungsstatus
    # ------------------------------------------------------------------

    def _read_execution_state(self) -> dict[str, Any] | None:
        if not self.state_path.exists():
            return None

        try:
            with self.state_path.open("r", encoding="utf-8") as file:
                state = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            raise OrderExecutionError(
                "Ausführungsstatus kann nicht zuverlässig gelesen werden. "
                "Orderausführung bleibt gesperrt."
            ) from exc

        if (
            not isinstance(state, dict)
            or state.get("status") != "PENDING_RECONCILIATION"
        ):
            raise OrderExecutionError(
                "Ausführungsstatus ist ungültig. "
                "Orderausführung bleibt gesperrt."
            )

        return state

    def _write_execution_state(self, state: dict[str, Any]) -> None:
        temporary_path = self.state_path.with_name(
            f"{self.state_path.name}.tmp"
        )

        try:
            self.state_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with temporary_path.open("w", encoding="utf-8") as file:
                json.dump(
                    state,
                    file,
                    ensure_ascii=False,
                    indent=2,
                )
                file.flush()
                os.fsync(file.fileno())

            os.replace(temporary_path, self.state_path)

        except OSError as exc:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

            raise OrderExecutionError(
                "Ausführungsstatus konnte nicht sicher gespeichert werden. "
                "Orderausführung wird abgebrochen."
            ) from exc

    def _ensure_not_blocked(self) -> None:
        state = self._read_execution_state()

        if state is not None:
            raise OrderExecutionError(
                "Orderausführung gesperrt: Eine vorherige Ausführung muss "
                "manuell abgeglichen werden. "
                f"Aktion={state.get('action', 'UNBEKANNT')}, "
                f"Ticker={state.get('ticker', 'UNBEKANNT')}, "
                f"Status={state.get('stage', 'UNBEKANNT')}. "
                "Reconciliation ausführen und Trading-212-Positionen sowie "
                "Orders prüfen."
            )

    def _mark_pending(
        self,
        action: str,
        ticker: str,
        quantity: float,
        stage: str,
    ) -> None:
        self._ensure_not_blocked()

        state = {
            "status": "PENDING_RECONCILIATION",
            "action": action,
            "ticker": ticker,
            "quantity": quantity,
            "stage": stage,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        self._write_execution_state(state)

        logger.warning(
            "Persistente Ausführungssperre gesetzt: "
            "%s %.6f %s, Status=%s",
            action,
            quantity,
            ticker,
            stage,
        )

    def _update_pending_stage(self, stage: str) -> None:
        state = self._read_execution_state()

        if state is None:
            raise OrderExecutionError(
                "Kein persistenter Ausführungsstatus vorhanden. "
                "Orderausführung wird abgebrochen."
            )

        state["stage"] = stage
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write_execution_state(state)

    def _clear_pending(self) -> None:
        try:
            self.state_path.unlink(missing_ok=True)
        except OSError as exc:
            raise OrderExecutionError(
                "Ausführung war möglicherweise erfolgreich, aber die "
                "persistente Sperre konnte nicht entfernt werden. "
                "Position und Orders manuell prüfen."
            ) from exc

        logger.info("Persistente Ausführungssperre aufgehoben.")

    def reconcile_pending_execution(self) -> dict[str, Any]:
        """
        Führt einen rein lesenden Abgleich einer gespeicherten Ausführung aus.

        Die Methode sendet oder storniert keine Orders und löscht niemals die
        persistente Sperre. Offene Orders allein belegen nicht, ob eine
        Marktorder ausgeführt, abgelehnt oder noch nicht sichtbar ist.
        """
        state = self._read_execution_state()

        if state is None:
            return {
                "status": "NO_PENDING_EXECUTION",
                "reconciled": False,
                "execution_blocked": False,
            }

        ticker = state.get("ticker")
        action = state.get("action")
        quantity = state.get("quantity")
        stage = state.get("stage")

        if (
            not isinstance(ticker, str)
            or not ticker.strip()
            or action not in {"BUY", "SELL"}
            or isinstance(quantity, bool)
            or not isinstance(quantity, (int, float))
            or not math.isfinite(quantity)
            or quantity <= 0
            or not isinstance(stage, str)
        ):
            raise OrderExecutionError(
                "Gespeicherter Ausführungsstatus enthält ungültige Daten. "
                "Die Sperre bleibt bestehen."
            )

        # Fehler bei einer der Abfragen werden absichtlich nicht abgefangen:
        # kein unvollständiger Befund und keine Änderung der Sperre.
        positions = self._get_positions()
        orders = self._get_orders()

        position = self._find_position(ticker, positions)
        matching_orders = [
            order
            for order in orders
            if self._get_instrument_ticker(order) == ticker
        ]

        position_quantity = (
            0.0
            if position is None
            else abs(self._number(position.get("quantity"), "quantity"))
        )

        unresolved_orders = [
            order
            for order in matching_orders
            if (
                str(order.get("status", "")).upper()
                in UNRESOLVED_ORDER_STATUSES
                or (
                    str(order.get("status", "")).upper()
                    in ACTIVE_ORDER_STATUSES
                    and str(order.get("type", "")).upper()
                    not in STOP_ORDER_TYPES
                )
            )
        ]

        active_stops = self._active_stops(ticker, matching_orders)

        if unresolved_orders:
            result_status = "UNRESOLVED_ORDERS"
        elif action == "BUY" and position_quantity > POSITION_QUANTITY_TOLERANCE:
            result_status = "BUY_POSITION_EXISTS_MANUAL_REVIEW"
        elif action == "SELL":
            result_status = "SELL_REQUIRES_MANUAL_REVIEW"
        else:
            result_status = "NO_CONCLUSIVE_EVIDENCE"

        result = {
            "status": result_status,
            "reconciled": False,
            "execution_blocked": True,
            "ticker": ticker,
            "action": action,
            "quantity": float(quantity),
            "stage": stage,
            "position_quantity": position_quantity,
            "position": position,
            "matching_orders": matching_orders,
            "unresolved_orders": unresolved_orders,
            "active_stops": active_stops,
        }

        logger.warning(
            "Reconciliation: ticker=%s action=%s stage=%s result=%s "
            "position_quantity=%.6f matching_orders=%d unresolved=%d "
            "active_stops=%d. Ausführungssperre bleibt bestehen.",
            ticker,
            action,
            stage,
            result_status,
            position_quantity,
            len(matching_orders),
            len(unresolved_orders),
            len(active_stops),
        )

        return result

    # ------------------------------------------------------------------
    # Allgemeine Sicherheitsprüfungen
    # ------------------------------------------------------------------

    def _require_demo_execution(self) -> None:
        base_url = getattr(self.trading212, "base_url", None)
        orders_enabled = getattr(
            self.trading212,
            "demo_orders_enabled",
            False,
        )

        if base_url != DEMO_BASE_URL:
            raise OrderExecutionError(
                "Sicherheitsabbruch: Nur die Trading-212-Demo-API ist erlaubt."
            )

        if orders_enabled is not True:
            raise OrderExecutionError(
                "Sicherheitsabbruch: Demo-Orderausführung ist nicht freigegeben."
            )

    def _get_positions(self) -> list[dict[str, Any]]:
        positions = self.trading212.get_positions()

        if not isinstance(positions, list):
            raise OrderExecutionError(
                "Ungültige Antwort bei Positionsabfrage."
            )

        if not all(isinstance(item, dict) for item in positions):
            raise OrderExecutionError(
                "Ungültiger Eintrag in der Positionsliste."
            )

        return positions

    def _get_orders(self) -> list[dict[str, Any]]:
        orders = self.trading212.get_pending_orders()

        if not isinstance(orders, list):
            raise OrderExecutionError(
                "Ungültige Antwort bei Orderabfrage."
            )

        if not all(isinstance(item, dict) for item in orders):
            raise OrderExecutionError(
                "Ungültiger Eintrag in der Orderliste."
            )

        return orders

    @staticmethod
    def _number(value: Any, field: str) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise OrderExecutionError(
                f"Ungültiger Zahlenwert: {field}."
            )

        return float(value)

    # ------------------------------------------------------------------
    # Ticker-Erkennung und Orderstatus
    # ------------------------------------------------------------------

    @staticmethod
    def _get_instrument_ticker(item: dict[str, Any]) -> Any:
        ticker = item.get("ticker")

        if isinstance(ticker, str):
            return ticker

        instrument = item.get("instrument")
        if isinstance(instrument, dict):
            return instrument.get("ticker")

        return None

    @staticmethod
    def _has_unresolved_orders(
        ticker: str,
        orders: list[dict[str, Any]],
    ) -> bool:
        for order in orders:
            if OrderExecutor._get_instrument_ticker(order) != ticker:
                continue

            status = str(order.get("status", "")).upper()

            if status in UNRESOLVED_ORDER_STATUSES:
                return True

        return False

    @staticmethod
    def _active_stops(
        ticker: str,
        orders: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            order
            for order in orders
            if OrderExecutor._get_instrument_ticker(order) == ticker
            and str(order.get("status", "")).upper()
            in ACTIVE_ORDER_STATUSES
            and str(order.get("type", "")).upper()
            in STOP_ORDER_TYPES
        ]

    def _find_position(
        self,
        ticker: str,
        positions: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        matches = [
            position
            for position in positions
            if self._get_instrument_ticker(position) == ticker
        ]

        if len(matches) > 1:
            raise OrderExecutionError(
                f"Mehrere Positionseinträge für {ticker}; Abbruch."
            )

        return matches[0] if matches else None

    def _get_position_quantity(
        self,
        ticker: str,
    ) -> tuple[dict[str, Any] | None, float]:
        position = self._find_position(
            ticker,
            self._get_positions(),
        )

        if position is None:
            return None, 0.0

        quantity = abs(
            self._number(
                position.get("quantity"),
                "quantity",
            )
        )

        return position, quantity

    def _wait_for_position(self, ticker: str) -> dict[str, Any]:
        for attempt in range(self.position_wait_attempts):
            position, quantity = self._get_position_quantity(ticker)

            if position is not None and quantity > 0:
                return position

            if attempt + 1 < self.position_wait_attempts:
                time.sleep(self.position_wait_interval)

        raise OrderExecutionError(
            f"Position {ticker} nach der Order nicht eindeutig sichtbar. "
            "Keine weitere Order wird automatisch gesendet."
        )

    def _wait_for_expected_quantity(
        self,
        ticker: str,
        expected_quantity: float,
    ) -> dict[str, Any] | None:
        tolerance = POSITION_QUANTITY_TOLERANCE

        for attempt in range(self.position_wait_attempts):
            position, observed_quantity = self._get_position_quantity(
                ticker
            )

            if abs(observed_quantity - expected_quantity) <= tolerance:
                return position

            logger.info(
                "Warte auf Positionsaktualisierung | Ticker=%s | "
                "Versuch=%s/%s | Erwartet=%.6f | Beobachtet=%.6f",
                ticker,
                attempt + 1,
                self.position_wait_attempts,
                expected_quantity,
                observed_quantity,
            )

            if attempt + 1 < self.position_wait_attempts:
                time.sleep(self.position_wait_interval)

        raise OrderExecutionError(
            f"Positionsmenge für {ticker} nicht bestätigt. "
            f"Erwartet={expected_quantity:.6f}. "
            "Die Ausführungssperre bleibt bestehen. "
            "Positionen und Orders manuell abgleichen."
        )

    # ------------------------------------------------------------------
    # Stop-Loss erstellen und verifizieren
    # ------------------------------------------------------------------

    @staticmethod
    def _get_average_price(position: dict[str, Any]) -> float:
        for field in ("averagePricePaid", "averagePrice"):
            value = position.get(field)

            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                and value > 0
            ):
                return float(value)

        raise OrderExecutionError(
            "Kein gültiger durchschnittlicher Einstandspreis in der "
            "Trading-212-Positionsantwort gefunden."
        )

    def _place_and_verify_stop(
        self,
        ticker: str,
        position: dict[str, Any],
    ) -> dict[str, Any]:
        quantity = abs(
            self._number(position.get("quantity"), "quantity")
        )
        average_price = self._get_average_price(position)
        current_price = self._number(
            position.get("currentPrice"),
            "currentPrice",
        )

        if quantity <= 0 or current_price <= 0:
            raise OrderExecutionError(
                "Position hat keine gültigen Mengen- oder Preisdaten."
            )

        stop_price = round(
            average_price * (1.0 - self.stop_loss_distance),
            6,
        )

        if stop_price >= current_price:
            raise OrderExecutionError(
                "Berechneter Stop-Loss liegt nicht unter dem aktuellen Kurs. "
                "Position muss manuell geprüft werden."
            )

        existing_orders = self._get_orders()

        if self._has_unresolved_orders(ticker, existing_orders):
            raise OrderExecutionError(
                f"Für {ticker} existiert eine Order mit ungeklärtem Status. "
                "Stop-Loss-Erstellung abgebrochen."
            )

        existing_stops = self._active_stops(ticker, existing_orders)

        if existing_stops:
            raise OrderExecutionError(
                f"Für {ticker} existiert bereits eine aktive Stop-Order. "
                "Keine zusätzliche Stop-Order wird angelegt."
            )

        self._update_pending_stage("SUBMITTING_STOP_LOSS")

        logger.info(
            "Erstelle Stop-Loss: %s, Menge %.6f, Stop-Preis %.6f",
            ticker,
            quantity,
            stop_price,
        )

        try:
            created_order = self.trading212.place_stop_order(
                ticker=ticker,
                quantity=-quantity,
                stop_price=stop_price,
                time_validity="GOOD_TILL_CANCEL",
            )
        except Exception:
            logger.critical(
                "Stop-Loss-Erstellung für %s fehlgeschlagen oder unklar. "
                "Position möglicherweise ungeschützt; manuelle Prüfung nötig.",
                ticker,
                exc_info=True,
            )
            raise

        if not isinstance(created_order, dict):
            raise OrderExecutionError(
                "Stop-Order-Antwort ist nicht eindeutig. "
                "Keine weitere Order wird gesendet."
            )

        created_order_id = created_order.get("id")

        if (
            isinstance(created_order_id, bool)
            or not isinstance(created_order_id, int)
            or created_order_id <= 0
        ):
            raise OrderExecutionError(
                "Die erstellte Stop-Order enthält keine gültige ID. "
                "Orderstatus manuell prüfen; keine weitere Order senden."
            )

        refreshed_orders = self._get_orders()

        if self._has_unresolved_orders(ticker, refreshed_orders):
            raise OrderExecutionError(
                "Nach der Stop-Order-Erstellung existiert eine Order mit "
                "ungeklärtem Status. Manuelle Prüfung erforderlich."
            )

        matching_stops = self._active_stops(ticker, refreshed_orders)

        if len(matching_stops) != 1:
            raise OrderExecutionError(
                "Stop-Loss konnte nach der Erstellung nicht eindeutig "
                "verifiziert werden. Manuelle Prüfung erforderlich."
            )

        verified_order = matching_stops[0]
        verified_order_id = verified_order.get("id")

        if (
            isinstance(verified_order_id, bool)
            or not isinstance(verified_order_id, int)
            or verified_order_id != created_order_id
        ):
            raise OrderExecutionError(
                "Die gefundene aktive Stop-Order stimmt nicht mit der "
                "erstellten Order-ID überein. "
                "Manuelle Prüfung erforderlich."
            )

        result = StopLossVerifier().verify(
            ticker,
            quantity,
            current_price,
            [verified_order],
        )

        if (
            getattr(result, "status", None) != "VERIFIED"
            or getattr(result, "approved", False) is not True
        ):
            raise OrderExecutionError(
                "Stop-Loss-Verifikation fehlgeschlagen: "
                f"{getattr(result, 'reason', 'Unbekannter Grund')}"
            )

        logger.info(
            "Stop-Loss verifiziert: %s | Order-ID=%s | Stop-Preis=%.6f",
            ticker,
            created_order_id,
            stop_price,
        )

        return {
            "ticker": ticker,
            "quantity": quantity,
            "stop_price": stop_price,
            "status": "VERIFIED",
            "order": verified_order,
        }

    # ------------------------------------------------------------------
    # Kauf
    # ------------------------------------------------------------------

    def _execute_buy(
        self,
        ticker: str,
        quantity: float,
    ) -> dict[str, Any]:
        positions = self._get_positions()
        existing_position = self._find_position(ticker, positions)
        orders = self._get_orders()

        if self._has_unresolved_orders(ticker, orders):
            raise OrderExecutionError(
                f"Für {ticker} existiert eine Order mit ungeklärtem Status. "
                "Kauf blockiert; manueller Abgleich erforderlich."
            )

        if existing_position is not None:
            existing_quantity = self._number(
                existing_position.get("quantity"),
                "quantity",
            )

            if abs(existing_quantity) > POSITION_QUANTITY_TOLERANCE:
                raise OrderExecutionError(
                    f"Für {ticker} besteht bereits eine Position. "
                    "Zusätzliche Käufe sind gesperrt, bis das Stop-Loss-"
                    "Management für Positionsaufstockungen implementiert ist."
                )

        if self._active_stops(ticker, orders):
            raise OrderExecutionError(
                f"Für {ticker} existiert bereits eine aktive Stop-Order. "
                "Kauf wird aus Sicherheitsgründen abgebrochen."
            )

        self._mark_pending(
            action="BUY",
            ticker=ticker,
            quantity=quantity,
            stage="SUBMITTING_MARKET_ORDER",
        )

        logger.warning("Demo-Kauforder: %s %.6f", ticker, quantity)

        # Exceptions bleiben absichtlich unhandled: die persistente Sperre
        # bleibt bei einem unklaren POST-Ergebnis erhalten.
        order = self.trading212.place_market_order(
            ticker=ticker,
            quantity=quantity,
        )

        if not isinstance(order, dict):
            raise OrderExecutionError(
                "Kauforder lieferte keine eindeutige Antwort. "
                "Orderstatus manuell prüfen; nicht erneut senden."
            )

        self._update_pending_stage("WAITING_FOR_BUY_POSITION")

        try:
            position = self._wait_for_position(ticker)
        except Exception:
            logger.critical(
                "Kauforder für %s wurde möglicherweise angenommen, aber "
                "die Position ist nicht eindeutig sichtbar. "
                "Orderstatus manuell prüfen.",
                ticker,
                exc_info=True,
            )
            raise

        try:
            stop_result = self._place_and_verify_stop(ticker, position)
        except Exception:
            logger.critical(
                "Kauf für %s wurde angenommen, Absicherung ist jedoch "
                "nicht bestätigt. Keine weiteren Orders automatisch senden.",
                ticker,
                exc_info=True,
            )
            raise

        return {
            "action": "BUY",
            "ticker": ticker,
            "order": order,
            "stop_loss": stop_result,
            "status": "EXECUTED_AND_PROTECTED",
        }

    # ------------------------------------------------------------------
    # Verkauf
    # ------------------------------------------------------------------

    def _execute_sell(
        self,
        ticker: str,
        quantity: float,
    ) -> dict[str, Any]:
        positions = self._get_positions()
        position = self._find_position(ticker, positions)

        if position is None:
            raise OrderExecutionError(
                f"Keine Position für {ticker}; Verkauf abgebrochen."
            )

        position_quantity = abs(
            self._number(position.get("quantity"), "quantity")
        )

        if position_quantity <= POSITION_QUANTITY_TOLERANCE:
            raise OrderExecutionError(
                f"Position für {ticker} hat keine verkaufbare Menge."
            )

        if quantity > position_quantity + POSITION_QUANTITY_TOLERANCE:
            raise OrderExecutionError(
                "Verkaufsmenge überschreitet die vorhandene Position."
            )

        expected_remaining_quantity = max(
            0.0,
            position_quantity - quantity,
        )

        if expected_remaining_quantity <= POSITION_QUANTITY_TOLERANCE:
            expected_remaining_quantity = 0.0

        orders = self._get_orders()

        if self._has_unresolved_orders(ticker, orders):
            raise OrderExecutionError(
                f"Für {ticker} existiert eine Order mit ungeklärtem Status. "
                "Verkauf blockiert; manueller Abgleich erforderlich."
            )

        active_stops = self._active_stops(ticker, orders)

        if len(active_stops) > 1:
            raise OrderExecutionError(
                f"Mehrere aktive Stop-Orders für {ticker}; "
                "manuelle Bereinigung erforderlich."
            )

        self._mark_pending(
            action="SELL",
            ticker=ticker,
            quantity=quantity,
            stage=(
                "CANCELLING_STOP_LOSS"
                if active_stops
                else "SUBMITTING_MARKET_SELL"
            ),
        )

        if active_stops:
            stop_order = active_stops[0]
            order_id = stop_order.get("id")

            if (
                isinstance(order_id, bool)
                or not isinstance(order_id, int)
                or order_id <= 0
            ):
                raise OrderExecutionError(
                    "Stop-Order hat keine gültige ID. Verkauf abgebrochen."
                )

            self.trading212.cancel_order(order_id)

            refreshed_orders = self._get_orders()

            if self._has_unresolved_orders(ticker, refreshed_orders):
                raise OrderExecutionError(
                    "Nach der Stop-Stornierung existiert eine Order mit "
                    "ungeklärtem Status. Verkauf abgebrochen."
                )

            remaining_stops = self._active_stops(ticker, refreshed_orders)

            if any(item.get("id") == order_id for item in remaining_stops):
                raise OrderExecutionError(
                    "Stop-Order-Stornierung konnte nicht bestätigt werden. "
                    "Verkauf wird nicht gesendet."
                )

            current_position, current_quantity = self._get_position_quantity(
                ticker
            )

            if (
                current_position is None
                or abs(current_quantity - position_quantity)
                > POSITION_QUANTITY_TOLERANCE
            ):
                raise OrderExecutionError(
                    "Position hat sich während der Stop-Stornierung geändert. "
                    "Möglicherweise wurde der Stop ausgelöst. "
                    "Market-Sell wird nicht gesendet; manueller Abgleich nötig."
                )

            self._update_pending_stage("SUBMITTING_MARKET_SELL")

        logger.warning(
            "Demo-Verkaufsorder: %s %.6f",
            ticker,
            quantity,
        )

        order = self.trading212.place_market_order(
            ticker=ticker,
            quantity=-quantity,
        )

        if not isinstance(order, dict):
            raise OrderExecutionError(
                "Verkaufsorder lieferte keine eindeutige Antwort. "
                "Orderstatus manuell prüfen; keine Wiederholung senden."
            )

        self._update_pending_stage("VERIFYING_REMAINING_POSITION")

        remaining_position = self._wait_for_expected_quantity(
            ticker,
            expected_remaining_quantity,
        )

        if expected_remaining_quantity == 0.0:
            remaining_orders = self._get_orders()

            if self._has_unresolved_orders(ticker, remaining_orders):
                raise OrderExecutionError(
                    "Position ist geschlossen, aber eine Order hat einen "
                    "ungeklärten Status. Manuelle Prüfung erforderlich."
                )

            remaining_stops = self._active_stops(ticker, remaining_orders)

            if remaining_stops:
                raise OrderExecutionError(
                    "Position ist geschlossen, aber es existiert weiterhin "
                    "eine aktive Stop-Order. Manuelle Prüfung erforderlich."
                )

            logger.info(
                "Verkauf verifiziert: Position %s vollständig geschlossen.",
                ticker,
            )

            return {
                "action": "SELL",
                "ticker": ticker,
                "order": order,
                "status": "EXECUTED",
                "position_verified": True,
                "remaining_quantity": 0.0,
            }

        if remaining_position is None:
            raise OrderExecutionError(
                "Erwartete Restposition ist nicht vorhanden. "
                "Die Ausführungssperre bleibt aktiv."
            )

        try:
            stop_result = self._place_and_verify_stop(
                ticker,
                remaining_position,
            )
        except Exception:
            logger.critical(
                "Verkauf für %s wurde bestätigt, aber die Restposition "
                "konnte nicht zuverlässig abgesichert werden. "
                "Die Ausführungssperre bleibt aktiv.",
                ticker,
                exc_info=True,
            )
            raise

        return {
            "action": "SELL",
            "ticker": ticker,
            "order": order,
            "status": "EXECUTED_AND_PROTECTED",
            "position_verified": True,
            "remaining_quantity": expected_remaining_quantity,
            "stop_loss": stop_result,
        }
