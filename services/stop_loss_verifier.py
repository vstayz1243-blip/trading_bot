
from dataclasses import dataclass
from math import isfinite
from typing import Any


@dataclass(frozen=True)
class StopLossResult:
    status: str
    approved: bool
    reason: str


class StopLossVerifier:
    # Nur bestätigte aktive Statuswerte gelten als Schutz.
    ACTIVE_STATUSES = {"NEW", "CONFIRMED"}

    # Diese Statuswerte gelten ausdrücklich als nicht mehr aktiv.
    TERMINAL_STATUSES = {
        "CANCELLED",
        "FILLED",
        "REJECTED",
        "EXPIRED",
    }

    STOP_ORDER_TYPES = {"STOP", "STOP_LIMIT"}
    QUANTITY_TOLERANCE = 1e-9

    @staticmethod
    def _valid_number(value: Any) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and isfinite(value)
        )

    @staticmethod
    def _get_ticker(order: dict[str, Any]) -> Any:
        ticker = order.get("ticker")

        if isinstance(ticker, str):
            return ticker

        instrument = order.get("instrument")
        if isinstance(instrument, dict):
            return instrument.get("ticker")

        return None

    def verify(
        self,
        ticker: str,
        position_quantity: float,
        current_price: float,
        orders: list[dict[str, Any]],
    ) -> StopLossResult:
        if not isinstance(ticker, str) or not ticker.strip():
            return self._unknown("Ticker ungültig.")

        ticker = ticker.strip()

        if (
            not self._valid_number(position_quantity)
            or position_quantity <= 0
        ):
            return self._unknown(
                "Keine gültige bestehende Position vorhanden."
            )

        if not self._valid_number(current_price) or current_price <= 0:
            return self._unknown("Aktueller Kurs ungültig.")

        if not isinstance(orders, list):
            return self._unknown("Orderliste ungültig.")

        candidates: list[dict[str, Any]] = []
        unresolved_stop_orders: list[dict[str, Any]] = []

        for order in orders:
            if not isinstance(order, dict):
                return self._unknown("Ungültiger Order-Eintrag.")

            order_ticker = self._get_ticker(order)

            # Orders anderer Instrumente beeinflussen diese Position nicht.
            if order_ticker != ticker:
                continue

            order_type = order.get("type")
            status = order.get("status")

            if not isinstance(order_type, str):
                return self._unknown(
                    "Ordertyp einer passenden Order fehlt oder ist ungültig."
                )

            normalized_type = order_type.upper()

            # Andere bekannte Ordertypen schützen die Position nicht.
            if normalized_type not in self.STOP_ORDER_TYPES:
                continue

            if not isinstance(status, str) or not status.strip():
                return self._unknown(
                    "Status einer passenden Stop-Order fehlt."
                )

            normalized_status = status.upper()

            if normalized_status in self.ACTIVE_STATUSES:
                candidates.append(order)
                continue

            if normalized_status in self.TERMINAL_STATUSES:
                continue

            # Unbekannter Status: nicht als aktiv und nicht als erledigt
            # interpretieren. Die Verifikation muss geschlossen scheitern.
            unresolved_stop_orders.append(order)

        if unresolved_stop_orders:
            statuses = [
                str(order.get("status", "<fehlt>"))
                for order in unresolved_stop_orders
            ]
            return self._unknown(
                "Mindestens eine passende Stop-Order besitzt einen "
                f"ungeklärten Status: {', '.join(statuses)}."
            )

        if not candidates:
            return self._missing(
                "Keine passende bestätigte aktive Stop-Order gefunden."
            )

        if len(candidates) != 1:
            return self._unknown(
                "Mehrere passende aktive Stop-Orders gefunden. "
                "Schutzstatus muss manuell geprüft werden."
            )

        order = candidates[0]

        quantity = order.get("quantity")
        filled_quantity = order.get("filledQuantity", 0)
        stop_price = order.get("stopPrice")
        side = order.get("side")

        if (
            not self._valid_number(quantity)
            or not self._valid_number(filled_quantity)
            or not self._valid_number(stop_price)
            or not isinstance(side, str)
        ):
            return self._unknown(
                "Stop-Order enthält unvollständige oder ungültige Daten."
            )

        if side.upper() != "SELL":
            return self._unknown(
                "Die Stop-Order ist keine Verkaufsorder."
            )

        total_quantity = abs(quantity)
        executed_quantity = abs(filled_quantity)

        if total_quantity <= 0:
            return self._unknown(
                "Stop-Order besitzt keine gültige Schutzmenge."
            )

        if executed_quantity > total_quantity:
            return self._unknown(
                "Ausgeführte Menge der Stop-Order ist ungültig."
            )

        if stop_price <= 0 or stop_price >= current_price:
            return self._unknown(
                "Stop-Preis muss positiv und unter dem aktuellen Kurs liegen."
            )

        remaining_quantity = total_quantity - executed_quantity

        if remaining_quantity <= self.QUANTITY_TOLERANCE:
            return self._missing(
                "Die Stop-Order hat keine verbleibende Schutzmenge."
            )

        if (
            remaining_quantity + self.QUANTITY_TOLERANCE
            < position_quantity
        ):
            return self._missing(
                "Die Stop-Order deckt die Position nicht vollständig ab. "
                f"Position={position_quantity:g}, "
                f"Schutzmenge={remaining_quantity:g}."
            )

        return StopLossResult(
            status="VERIFIED",
            approved=True,
            reason=(
                "Aktive Verkaufs-Stop-Order verifiziert: "
                f"{remaining_quantity:g} von "
                f"{position_quantity:g} Stück abgesichert."
            ),
        )

    @staticmethod
    def _unknown(reason: str) -> StopLossResult:
        return StopLossResult(
            status="UNKNOWN",
            approved=False,
            reason=reason,
        )

    @staticmethod
    def _missing(reason: str) -> StopLossResult:
        return StopLossResult(
            status="MISSING",
            approved=False,
            reason=reason,
        )
