from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from client.trading212 import DEMO_BASE_URL, Trading212Client


def main() -> int:
    client = Trading212Client(
        credentials_path=str(PROJECT_ROOT / "credentials.json"),
        demo_orders_enabled=False,
    )

    try:
        assert client.base_url == DEMO_BASE_URL, "Falsche API-Basis-URL"
        assert client.demo_orders_enabled is False, "Orderfreigabe ist aktiviert"

        print("Demo-API:", client.base_url)
        print("Orderfreigabe:", client.demo_orders_enabled)

        account = client.get_account_summary()
        positions = client.get_positions()
        orders = client.get_pending_orders()

        print("\nKontodaten erfolgreich abgerufen.")
        print("Kontofelder:", sorted(account.keys()))
        print("Anzahl Positionen:", len(positions))
        print("Anzahl offener Orders:", len(orders))
        print("\nREAD-ONLY-TEST ERFOLGREICH")
        print("Es wurden keine Orders erstellt oder storniert.")
        return 0

    except Exception as exc:
        print(f"\nREAD-ONLY-TEST FEHLGESCHLAGEN: {type(exc).__name__}")
        print(str(exc))
        return 1

    finally:
        client.session.close()


if __name__ == "__main__":
    raise SystemExit(main())
