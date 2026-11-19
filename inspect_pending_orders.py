
import json

from client.trading212 import Trading212Client


def main() -> None:
    client = Trading212Client("credentials.json")

    try:
        orders = client.get_pending_orders()

        print(f"Anzahl offener Orders: {len(orders)}")

        if not orders:
            print(
                "Keine offenen Orders vorhanden. "
                "Stop-Loss-Verhalten kann damit nicht "
                "an einer realen Order geprüft werden."
            )
            return

        for index, order in enumerate(orders, start=1):
            print(f"\n--- Order {index} ---")
            print(
                json.dumps(
                    order,
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                )
            )

    finally:
        client.session.close()


if __name__ == "__main__":

    main()