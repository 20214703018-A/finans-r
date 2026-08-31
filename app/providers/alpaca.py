"""Alpaca provider – Nasdaq/NYSE (IEX in free tier; SIP in paid)."""
import httpx
from datetime import datetime, timezone
from app.providers.base import MarketDataProvider, Bar, TIMEFRAMES
from app.config import settings

ALPACA_TF_MAP = {
    "15m": "15Min",
    "1h": "1Hour",
    "4h": "4Hour",
    "1d": "1Day",
}


class AlpacaProvider(MarketDataProvider):
    name = "alpaca"

    def __init__(self, api_key: str | None = None, api_secret: str | None = None, base_url: str | None = None):
        self.api_key = api_key or settings.alpaca_api_key
        self.api_secret = api_secret or settings.alpaca_api_secret
        self.base_url = (base_url or "https://data.alpaca.markets").rstrip("/")

    async def get_bars(self, symbol: str, timeframe: str, limit: int = 300) -> list[Bar]:
        if not self.api_key or not self.api_secret:
            raise RuntimeError("Alpaca API credentials not configured")
        if timeframe not in ALPACA_TF_MAP:
            raise ValueError(f"Unsupported timeframe {timeframe}")
        tf = ALPACA_TF_MAP[timeframe]
        # data v2 endpoint
        url = f"{self.base_url}/v2/stocks/{symbol}/bars"
        headers = {"APCA-API-KEY-ID": self.api_key, "APCA-API-SECRET-KEY": self.api_secret}
        params = {"timeframe": tf, "limit": limit, "adjustment": "raw", "feed": "iex", "sort": "asc"}
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
        bars = []
        for b in data.get("bars", []):
            ts = datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(timezone.utc)
            bars.append(
                Bar(
                    asset_id=f"{symbol}.XNAS",
                    symbol=symbol,
                    exchange="ALPACA",
                    timeframe=timeframe,
                    timestamp=ts,
                    open=float(b["o"]),
                    high=float(b["h"]),
                    low=float(b["l"]),
                    close=float(b["c"]),
                    volume=float(b["v"]),
                )
            )
        return bars
