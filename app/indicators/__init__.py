from app.indicators.trend import add_trend_indicators, classify_trend
from app.indicators.momentum import add_momentum_indicators, detect_rsi_divergence, rsi, stochastic, cci, williams_r
from app.indicators.volatility import add_volatility_indicators, atr
from app.indicators.volume import add_volume_indicators, add_vwap, rvol_label
from app.indicators.macd import add_macd, macd_state
from app.indicators.bands import add_bands_indicators, detect_squeeze_breakout, bollinger_bands, keltner_channel, donchian_channel
from app.indicators.fibonacci import add_fibonacci_indicators, detect_fibonacci_clusters, calculate_fibonacci_retracement
import polars as pl


def calculate_indicators(df: pl.DataFrame) -> pl.DataFrame:
    df = add_trend_indicators(df)
    df = add_momentum_indicators(df)
    df = add_volatility_indicators(df)
    df = add_volume_indicators(df)
    df = add_vwap(df)
    df = add_macd(df)
    df = add_bands_indicators(df)  # Bollinger, Keltner, Donchian bantları
    df = add_fibonacci_indicators(df)  # Fibonacci seviyeleri
    return df


__all__ = [
    "calculate_indicators",
    "add_trend_indicators",
    "classify_trend",
    "add_momentum_indicators",
    "detect_rsi_divergence",
    "rsi",
    "stochastic",
    "cci",
    "williams_r",
    "add_volatility_indicators",
    "atr",
    "add_volume_indicators",
    "add_vwap",
    "rvol_label",
    "add_bands_indicators",
    "detect_squeeze_breakout",
    "bollinger_bands",
    "keltner_channel",
    "donchian_channel",
    "add_fibonacci_indicators",
    "detect_fibonacci_clusters",
    "calculate_fibonacci_retracement",
]
