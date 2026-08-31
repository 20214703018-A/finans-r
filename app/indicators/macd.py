"""MACD Engine – EMA12/26/9, histogram. Tüm hesaplama deterministik."""
import polars as pl
import numpy as np
from app.indicators.trend import ema

def add_macd(df: pl.DataFrame, fast=12, slow=26, signal=9) -> pl.DataFrame:
    close = df["close"].to_numpy().astype(float)
    n = len(close)
    if n < slow + signal:
        df = df.with_columns(
            pl.Series("macd", np.full(n, np.nan)),
            pl.Series("macd_signal", np.full(n, np.nan)),
            pl.Series("macd_hist", np.full(n, np.nan)),
        )
        return df
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    macd = ema_fast - ema_slow
    sig = ema(macd, signal)
    hist = macd - sig
    df = df.with_columns(
        pl.Series("macd", macd),
        pl.Series("macd_signal", sig),
        pl.Series("macd_hist", hist),
    )
    return df

def macd_state(last: dict) -> dict:
    """Son bar MACD yorumu deterministik."""
    import math
    def safe(v):
        if v is None or (isinstance(v,float) and math.isnan(v)): return None
        return float(v)
    m = safe(last.get("macd")); s = safe(last.get("macd_signal")); h = safe(last.get("macd_hist"))
    if m is None or s is None or h is None:
        return {"signal":"nötr","cross": None, "momentum": None}
    cross = None
    # histogram işaret değişimi ile cross tespiti için hist önceki bar gerek – pipeline'da df'ten bakılır, burada sadece anlık
    if m > s and h > 0:
        signal = "bullish"
        cross = "golden" if h > 0 else None
    elif m < s and h < 0:
        signal = "bearish"
        cross = "death" if h < 0 else None
    else:
        signal = "nötr"
    mom = "güçleniyor" if abs(h) > abs(m*0.02) else "zayıf"
    return {"signal": signal, "cross": cross, "hist": h, "macd": m, "signal_line": s, "momentum": mom}
