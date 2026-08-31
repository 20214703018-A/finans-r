"""Momentum Engine §15 – RSI14 + divergence."""
import polars as pl
import numpy as np
from scipy.signal import find_peaks


def rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(close)
    out = np.full(n, np.nan)
    if n <= period:
        return out
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    # Wilder
    avg_gain = np.full(n, np.nan)
    avg_loss = np.full(n, np.nan)
    avg_gain[period] = gain[1 : period + 1].mean()
    avg_loss[period] = loss[1 : period + 1].mean()
    for i in range(period + 1, n):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss[i]) / period
    rs = avg_gain / (avg_loss + 1e-12)
    out[period:] = 100 - (100 / (1 + rs[period:]))
    return out


def add_momentum_indicators(df: pl.DataFrame) -> pl.DataFrame:
    close = df["close"].to_numpy().astype(float)
    r = rsi(close, 14)
    return df.with_columns(pl.Series("rsi", r))


def detect_rsi_divergence(df: pl.DataFrame) -> dict:
    """Simple bullish/bearish divergence check on last ~40 bars."""
    if df.height < 30 or "rsi" not in df.columns:
        return {"bullish_divergence": False, "bearish_divergence": False}
    close = df["close"].to_numpy()
    rsi_s = df["rsi"].to_numpy()
    # Find price lows and RSI lows
    # Bullish: price lower low but RSI higher low
    # Use last two swing lows
    lows_idx, _ = find_peaks(-close, distance=5)
    if len(lows_idx) < 2:
        return {"bullish_divergence": False, "bearish_divergence": False}
    i1, i2 = lows_idx[-2], lows_idx[-1]
    bullish = close[i2] < close[i1] and rsi_s[i2] > rsi_s[i1] and not np.isnan(rsi_s[i1]) and not np.isnan(rsi_s[i2])

    highs_idx, _ = find_peaks(close, distance=5)
    bearish = False
    if len(highs_idx) >= 2:
        j1, j2 = highs_idx[-2], highs_idx[-1]
        bearish = close[j2] > close[j1] and rsi_s[j2] < rsi_s[j1] and not np.isnan(rsi_s[j1]) and not np.isnan(rsi_s[j2])

    return {"bullish_divergence": bool(bullish), "bearish_divergence": bool(bearish)}
