import asyncio

from bot.trading_bot import TradingBot


async def main():

    bot = TradingBot(
        credentials_path="credentials.json",
        interval=300,
        ticker="AAPL_US_EQ",
    )

    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())