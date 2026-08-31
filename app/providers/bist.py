"""BIST provider – stub until licensed vendor (Matriks/İdeal) is integrated.
For MVP EOD test, TwelveData or historical dataset can be plugged here.
Currently raises NotImplementedError with actionable message.
"""
from app.providers.base import MarketDataProvider, Bar


class BistProvider(MarketDataProvider):
    name = "bist"

    async def get_bars(self, symbol: str, timeframe: str, limit: int = 300) -> list[Bar]:
        raise NotImplementedError(
            "BIST intraday requires licensed vendor (Matriks/İdeal). "
            "For MVP EOD test plug TwelveData here. Symbol: " + symbol
        )
