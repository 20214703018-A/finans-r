"""Volume Engine §17 – RVOL, OBV, volume trend + VWAP §18."""
import polars as pl
import numpy as np


def add_volume_indicators(df: pl.DataFrame) -> pl.DataFrame:
    vol = df["volume"].to_numpy().astype(float)
    close = df["close"].to_numpy().astype(float)
    n = len(vol)
    # RVOL = current / SMA20
    rvol = np.full(n, np.nan)
    window = 20
    for i in range(window - 1, n):
        sma = vol[i - window + 1 : i + 1].mean()
        rvol[i] = vol[i] / (sma + 1e-12)
    # OBV
    obv = np.zeros(n)
    for i in range(1, n):
        if close[i] > close[i - 1]:
            obv[i] = obv[i - 1] + vol[i]
        elif close[i] < close[i - 1]:
            obv[i] = obv[i - 1] - vol[i]
        else:
            obv[i] = obv[i - 1]
    # Volume trend: slope of 20-bar SMA
    vol_sma = np.full(n, np.nan)
    for i in range(window - 1, n):
        vol_sma[i] = vol[i - window + 1 : i + 1].mean()
    vol_trend = np.full(n, np.nan)
    if n >= window + 5:
        for i in range(window + 4, n):
            if not np.isnan(vol_sma[i]) and not np.isnan(vol_sma[i - 5]):
                vol_trend[i] = (vol_sma[i] - vol_sma[i - 5]) / (vol_sma[i - 5] + 1e-12)

    df = df.with_columns(
        pl.Series("rvol", rvol),
        pl.Series("obv", obv),
        pl.Series("vol_sma20", vol_sma),
        pl.Series("vol_trend", vol_trend),
    )
    return df


def add_vwap(df: pl.DataFrame) -> pl.DataFrame:
    """Rolling VWAP – anchored to session start or rolling 20 for crypto (24/7)."""
    high = df["high"].to_numpy().astype(float)
    low = df["low"].to_numpy().astype(float)
    close = df["close"].to_numpy().astype(float)
    vol = df["volume"].to_numpy().astype(float)
    typical = (high + low + close) / 3
    # For MVP crypto, use rolling 20 VWAP (since no session)
    n = len(df)
    vwap = np.full(n, np.nan)
    window = 20
    for i in range(window - 1, n):
        pv = (typical[i - window + 1 : i + 1] * vol[i - window + 1 : i + 1]).sum()
        vv = vol[i - window + 1 : i + 1].sum()
        vwap[i] = pv / (vv + 1e-12)
    return df.with_columns(pl.Series("vwap", vwap))


def rvol_label(rvol: float) -> str:
    if rvol is None or (isinstance(rvol, float) and np.isnan(rvol)):
        return "unknown"
    if rvol < 0.8:
        return "weak"
    if rvol < 1.2:
        return "normal"
    if rvol < 1.5:
        return "strong"
    return "very_strong"
