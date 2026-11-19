from client.trading212 import Trading212Client


class PositionsClient:

    def __init__(self, client: Trading212Client):
        self.client = client

    def get_all(self):
        positions = self.client.get(
            "/equity/positions"
        )

        if positions is None:
            return []

        return positions

    def get_position(self, ticker: str):
        positions = self.get_all()

        for position in positions:
            instrument = position.get("instrument", {})
            
            if instrument.get("ticker") == ticker:
                return position

        return None