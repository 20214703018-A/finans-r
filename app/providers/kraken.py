import httpx
from datetime import datetime, timezone
from app.providers.base import MarketDataProvider, Bar, TIMEFRAMES
from app.config import settings

# Kraken pair mapping: our symbol -> Kraken pair name
# Kraken OHLC endpoint accepts e.g. XBTUSD, ETHUSD etc.
# We normalize via mapping; fallback tries as-is.
KRAKEN_PAIR_MAP: dict[str, str] = {
    "BTCUSD": "XBTUSD",
    "ETHUSD": "ETHUSD",
    "SOLUSD": "SOLUSD",
    "XRPUSD": "XRPUSD",
    "BNBUSD": "BNBUSD",
    "DOGEUSD": "XDGUSD",  # Kraken uses XDG for DOGE
    "ADAUSD": "ADAUSD",
    "AVAXUSD": "AVAXUSD",
    "LINKUSD": "LINKUSD",
    "SUIUSD": "SUIUSD",
}

KRAKEN_INTERVAL_MAP: dict[str, int] = {
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


class KrakenProvider(MarketDataProvider):
    name = "kraken"

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.kraken_base_url).rstrip("/")

    async def get_bars(self, symbol: str, timeframe: str, limit: int = 300) -> list[Bar]:
        if timeframe not in TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe {timeframe}. Allowed: {list(TIMEFRAMES)}")
        pair = KRAKEN_PAIR_MAP.get(symbol, symbol)
        interval = KRAKEN_INTERVAL_MAP[timeframe]

        url = f"{self.base_url}/0/public/OHLC"
        params = {"pair": pair, "interval": interval}

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        if data.get("error"):
            # Kraken returns error array; e.g. ["EQuery:Unknown asset pair"]
            raise RuntimeError(f"Kraken error for {symbol}/{timeframe}: {data['error']}")

        result = data.get("result", {})
        # result contains pair key + last; pick first non-"last" key
        ohlc_key = next((k for k in result.keys() if k != "last"), None)
        if ohlc_key is None:
            raise RuntimeError(f"Kraken: no OHLC data for {symbol}")

        raw = result[ohlc_key]  # list of [time, open, high, low, close, vwap, volume, count]
        # Kraken returns oldest first; ensure sorted
        bars: list[Bar] = []
        for row in raw:
            ts = datetime.fromtimestamp(int(row[0]), tz=timezone.utc)
            bars.append(
                Bar(
                    asset_id=f"{symbol}.KRAKEN",
                    symbol=symbol,
                    exchange="KRAKEN",
                    timeframe=timeframe,
                    timestamp=ts,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[6]),
                )
            )
        # limit to most recent `limit` bars
        if len(bars) > limit:
            bars = bars[-limit:]
        return bars
