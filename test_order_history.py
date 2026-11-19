
import logging

from client.history import HistoryClient
from client.trading212 import Trading212Client


logging.basicConfig(level=logging.INFO)


def main() -> None:
    client = Trading212Client(
        credentials_path="credentials.json",
        base_url="https://demo.trading212.com/api/v0",
    )

    try:
        history = HistoryClient(client)
        items = history.get_order_items(limit=20)

        print(f"Anzahl historischer Orders: {len(items)}")
        print("-" * 70)

        for index, item in enumerate(items, start=1):
            order = item.get("order")

            if not isinstance(order, dict):
                print(f"Order {index}: Ungültiges Order-Format")
                continue

            print(f"Order {index}")
            print(f"  ID:               {order.get('id', 'unbekannt')}")
            print(f"  Ticker:           {order.get('ticker', 'unbekannt')}")
            print(f"  Typ:              {order.get('type', 'unbekannt')}")
            print(f"  Seite:            {order.get('side', 'unbekannt')}")
            print(f"  Status:           {order.get('status', 'unbekannt')}")
            print(f"  Menge:            {order.get('quantity', 'unbekannt')}")
            print(f"  Ausgeführt:       {order.get('filledQuantity', 'unbekannt')}")
            print(f"  Erstellt am:      {order.get('createdAt', 'unbekannt')}")
            print()

        print("Stop-Loss-Status: NICHT AUS DIESER HISTORIE ABGELEITET")
        print("Historische Orders belegen keinen aktuell aktiven Stop-Loss.")

    except Exception:
        logging.exception("Orderhistorie konnte nicht ausgewertet werden.")
        raise

    finally:
        client.session.close()


if __name__ == "__main__":
    main()
