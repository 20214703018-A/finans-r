"""Market Regime Engine §29."""
import polars as pl
import numpy as np


def evaluate_regime(df: pl.DataFrame) -> dict:
    """
    Returns regime label and components.
    Inputs: adx, atr_pct, ema20_slope, close/ema200
    """
    if df.height < 2:
        return {"regime": "RANGE", "adx": None, "atr_pct": None, "ema_slope": None}
    last = df.row(-1, named=True)
    adx = last.get("adx")
    atr_pct = last.get("atr_pct")
    slope = last.get("ema20_slope")
    close = last.get("close")
    ema200 = last.get("ema200")

    # Normalize NaNs
    def is_valid(v):
        return v is not None and not (isinstance(v, float) and np.isnan(v))

    adx_v = adx if is_valid(adx) else 15
    atr_pct_v = atr_pct if is_valid(atr_pct) else 50
    slope_v = slope if is_valid(slope) else 0

    # Distance from EMA200
    ema_dist = None
    if is_valid(ema200) and is_valid(close) and ema200 != 0:
        ema_dist = (close - ema200) / ema200 * 100

    # High/Low volatility by ATR percentile
    vol_label = "normal"
    if is_valid(atr_pct):
        if atr_pct > 75:
            vol_label = "HIGH_VOLATILITY"
        elif atr_pct < 25:
            vol_label = "LOW_VOLATILITY"

    # Trend regime by ADX + slope
    if adx_v > 25 and slope_v > 0.15:
        regime = "TRENDING_UP"
    elif adx_v > 25 and slope_v < -0.15:
        regime = "TRENDING_DOWN"
    elif vol_label == "HIGH_VOLATILITY":
        regime = "HIGH_VOLATILITY"
    elif vol_label == "LOW_VOLATILITY" and adx_v < 20:
        regime = "RANGE"
    else:
        regime = "RANGE"

    return {
        "regime": regime,
        "adx": float(adx) if is_valid(adx) else None,
        "atr_pct": float(atr_pct) if is_valid(atr_pct) else None,
        "ema20_slope": float(slope) if is_valid(slope) else None,
        "close_ema200_dist_pct": float(ema_dist) if ema_dist is not None else None,
        "volatility": vol_label,
    }
