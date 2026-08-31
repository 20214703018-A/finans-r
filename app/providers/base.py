from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Timeframe = Literal["15m", "1h", "4h", "1d"]


@dataclass(frozen=True)
class Bar:
    asset_id: str         # e.g. BTCUSD.KRAKEN
    symbol: str           # e.g. BTCUSD
    exchange: str         # e.g. KRAKEN
    timeframe: str        # e.g. 4h
    timestamp: datetime   # UTC, candle open time
    open: float
    high: float
    low: float
    close: float
    volume: float


# Mapping timeframe -> Kraken interval & canonical minutes
TIMEFRAMES: dict[str, int] = {
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}

# Provider routing – decide which provider serves which asset prefix
PROVIDER_ROUTING: dict[str, str] = {
    "KRAKEN": "kraken",
    "ALPACA": "alpaca",
    "BIST": "bist",
}


class MarketDataProvider(ABC):
    """Abstract provider – all providers must return normalized Bar list sorted asc by timestamp."""

    name: str = "base"

    @abstractmethod
    async def get_bars(self, symbol: str, timeframe: str, limit: int = 300) -> list[Bar]:
        ...

    def asset_id(self, symbol: str, exchange: str) -> str:
        return f"{symbol}.{exchange}"
