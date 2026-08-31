"""Volatility Engine §16 – ATR14 + ATR percentile."""
import polars as pl
import numpy as np


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(close)
    out = np.full(n, np.nan)
    if n < 2:
        return out
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    # Wilder smoothing
    out[period - 1] = np.nanmean(tr[:period])
    for i in range(period, n):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out


def add_volatility_indicators(df: pl.DataFrame) -> pl.DataFrame:
    high = df["high"].to_numpy().astype(float)
    low = df["low"].to_numpy().astype(float)
    close = df["close"].to_numpy().astype(float)
    a = atr(high, low, close, 14)
    # ATR percentile (rolling 100)
    pct = np.full(len(a), np.nan)
    window = 100
    for i in range(window - 1, len(a)):
        w = a[i - window + 1 : i + 1]
        w = w[~np.isnan(w)]
        if len(w) == 0:
            continue
        # percentile of current vs window
        cur = a[i]
        if np.isnan(cur):
            continue
        pct[i] = (w < cur).mean() * 100
    df = df.with_columns(pl.Series("atr", a), pl.Series("atr_pct", pct))
    return df
