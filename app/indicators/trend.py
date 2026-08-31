"""Trend Engine §14 – EMA20/50/200, ADX, EMA slope."""
import polars as pl
import numpy as np


def ema(series: np.ndarray, period: int) -> np.ndarray:
    alpha = 2 / (period + 1)
    out = np.empty_like(series, dtype=float)
    out[0] = series[0]
    for i in range(1, len(series)):
        out[i] = alpha * series[i] + (1 - alpha) * out[i - 1]
    return out


def compute_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(close)
    if n < period + 1:
        return np.full(n, np.nan)
    tr = np.maximum(high[1:] - low[1:], np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
    tr = np.concatenate([[np.nan], tr])
    # directional movement
    up = high[1:] - high[:-1]
    dn = low[:-1] - low[1:]
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    plus_dm = np.concatenate([[np.nan], plus_dm])
    minus_dm = np.concatenate([[np.nan], minus_dm])

    # Wilder smoothing
    def wilder(a, p):
        out = np.full_like(a, np.nan, dtype=float)
        # first valid
        first = p
        # find first non-nan
        valid = ~np.isnan(a)
        idx = np.where(valid)[0]
        if len(idx) < p:
            return out
        # seed: sum of first p
        s = np.nansum(a[idx[:p]])
        out[idx[p - 1]] = s
        for i in range(idx[p - 1] + 1, n):
            if np.isnan(a[i]):
                out[i] = out[i - 1]
            else:
                out[i] = out[i - 1] - out[i - 1] / p + a[i]
        return out

    atr_w = wilder(tr, period)
    plus_w = wilder(plus_dm, period)
    minus_w = wilder(minus_dm, period)
    plus_di = 100 * plus_w / atr_w
    minus_di = 100 * minus_w / atr_w
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-12)
    adx = wilder(dx, period)
    return adx


def add_trend_indicators(df: pl.DataFrame) -> pl.DataFrame:
    close = df["close"].to_numpy().astype(float)
    high = df["high"].to_numpy().astype(float)
    low = df["low"].to_numpy().astype(float)
    n = len(close)
    ema20 = ema(close, 20) if n >= 20 else np.full(n, np.nan)
    ema50 = ema(close, 50) if n >= 50 else np.full(n, np.nan)
    ema200 = ema(close, 200) if n >= 200 else np.full(n, np.nan)
    adx = compute_adx(high, low, close, 14)
    # EMA slope: % change of ema20 over 5 bars
    slope = np.full(n, np.nan)
    if n >= 6:
        slope[5:] = (ema20[5:] - ema20[:-5]) / (ema20[:-5] + 1e-12) * 100

    df = df.with_columns(
        pl.Series("ema20", ema20),
        pl.Series("ema50", ema50),
        pl.Series("ema200", ema200),
        pl.Series("adx", adx),
        pl.Series("ema20_slope", slope),
    )
    return df


def classify_trend(row: dict) -> str:
    c, e20, e50, e200, adx = row["close"], row["ema20"], row["ema50"], row["ema200"], row["adx"]
    if any(v is None or (isinstance(v, float) and np.isnan(v)) for v in [e20, e50, e200, adx]):
        # fallback without ema200
        if e20 is not None and e50 is not None and not np.isnan(e20) and not np.isnan(e50):
            if c > e20 > e50:
                return "UPTREND" if adx < 25 else "STRONG_UPTREND"
            if c < e20 < e50:
                return "DOWNTREND" if adx < 25 else "STRONG_DOWNTREND"
        return "RANGE"
    if c > e20 > e50 > e200 and adx > 25:
        return "STRONG_UPTREND"
    if c > e20 > e50:
        return "UPTREND"
    if c < e20 < e50 < e200 and adx > 25:
        return "STRONG_DOWNTREND"
    if c < e20 < e50:
        return "DOWNTREND"
    return "RANGE"
