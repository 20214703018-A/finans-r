from app.providers.base import Bar, TIMEFRAMES, MarketDataProvider
from app.providers.kraken import KrakenProvider
from app.providers.alpaca import AlpacaProvider
from app.providers.bist import BistProvider

PROVIDERS: dict[str, MarketDataProvider] = {
    "kraken": KrakenProvider(),
    "alpaca": AlpacaProvider(),
    "bist": BistProvider(),
}

# Symbol -> provider key routing (MVP: crypto->kraken, US equity->alpaca, TR equity->bist)
SYMBOL_PROVIDER_MAP: dict[str, str] = {
    "BTCUSD": "kraken",
    "ETHUSD": "kraken",
    "SOLUSD": "kraken",
    "XRPUSD": "kraken",
    "BNBUSD": "kraken",
    "DOGEUSD": "kraken",
    "ADAUSD": "kraken",
    "AVAXUSD": "kraken",
    "LINKUSD": "kraken",
    "SUIUSD": "kraken",
    "AAPL": "alpaca",
    "MSFT": "alpaca",
    "NVDA": "alpaca",
    "TSLA": "alpaca",
    "THYAO": "bist",
    "GARAN": "bist",
    "AKBNK": "bist",
}


def get_provider_for_symbol(symbol: str) -> MarketDataProvider:
    key = SYMBOL_PROVIDER_MAP.get(symbol)
    if key is None:
        # Default heuristic: ends with USD or USDT -> kraken
        if symbol.endswith("USD") or symbol.endswith("USDT"):
            key = "kraken"
        elif "/" in symbol:
            # Handle symbols like BTC/USDT, ETH/USD
            base = symbol.split("/")[0]
            if base in ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "AVAX", "LINK", "SUI"]:
                key = "kraken"
            else:
                key = "kraken"  # Default to kraken for unknown crypto
        else:
            raise ValueError(f"No provider configured for symbol {symbol}")
    return PROVIDERS[key]


__all__ = ["Bar", "TIMEFRAMES", "MarketDataProvider", "PROVIDERS", "get_provider_for_symbol"]
