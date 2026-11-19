
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from client.trading212 import DEMO_BASE_URL, Trading212Client


def print_json(label: str, data: Any) -> None:
    print(f"\n--- {label} ---")
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def main() -> int:
    client = Trading212Client(
        credentials_path=str(PROJECT_ROOT / "credentials.json"),
        demo_orders_enabled=False,
    )

    try:
        if client.base_url != DEMO_BASE_URL:
            raise RuntimeError("Abbruch: Unerwartete API-Basis-URL.")

        if client.demo_orders_enabled is not False:
            raise RuntimeError("Abbruch: Orderfreigabe ist aktiviert.")

        print("API:", client.base_url)
        print("Orderfreigabe:", client.demo_orders_enabled)
        print("\nLese Kontodaten ...")

        account = client.get_account_summary()
        positions = client.get_positions()
        orders = client.get_pending_orders()

        print_json("Kontodaten", account)

        print(f"\n--- Positionen ({len(positions)}) ---")
        for position in positions:
            print_json("Position", position)

        print(f"\n--- Offene Orders ({len(orders)}) ---")
        for order in orders:
            print_json("Order", order)

        print("\nREAD-ONLY-TEST ERFOLGREICH")
        print("Es wurden keine Orders erstellt oder storniert.")
        return 0

    except Exception as exc:
        print(
            f"\nREAD-ONLY-TEST FEHLGESCHLAGEN: "
            f"{type(exc).__name__}"
        )
        print(str(exc))
        return 1

    finally:
        client.session.close()


if __name__ == "__main__":
    raise SystemExit(main())
