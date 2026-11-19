
from pprint import pprint

from client.trading212 import Trading212Client


def main():
    client = Trading212Client()

    try:
        orders = client.get_pending_orders()

        print("\n=== PENDING ORDERS ===")
        print(f"Anzahl: {len(orders)}")

        for order in orders:
            pprint(order)
            print("-" * 60)

    finally:
        client.close()


if __name__ == "__main__":
    main()
