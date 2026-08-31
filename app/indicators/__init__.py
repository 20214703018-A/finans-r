from app.indicators.trend import add_trend_indicators, classify_trend
from app.indicators.momentum import add_momentum_indicators, detect_rsi_divergence, rsi
from app.indicators.volatility import add_volatility_indicators, atr
from app.indicators.volume import add_volume_indicators, add_vwap, rvol_label
from app.indicators.macd import add_macd, macd_state
import polars as pl


def calculate_indicators(df: pl.DataFrame) -> pl.DataFrame:
    df = add_trend_indicators(df)
    df = add_momentum_indicators(df)
    df = add_volatility_indicators(df)
    df = add_volume_indicators(df)
    df = add_vwap(df)
    df = add_macd(df)
    return df


__all__ = [
    "calculate_indicators",
    "add_trend_indicators",
    "classify_trend",
    "add_momentum_indicators",
    "detect_rsi_divergence",
    "rsi",
    "add_volatility_indicators",
    "atr",
    "add_volume_indicators",
    "add_vwap",
    "rvol_label",
]
