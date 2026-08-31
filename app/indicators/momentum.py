"""Momentum Engine §15 – RSI14 + Stochastic + CCI + Williams %R + improved divergence."""
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
    # Wilder smoothing
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


def stochastic(high: np.ndarray, low: np.ndarray, close: np.ndarray, k_period: int = 14, d_period: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """Stochastic Oscillator %K and %D."""
    n = len(close)
    k = np.full(n, np.nan)
    for i in range(k_period - 1, n):
        lowest_low = low[i - k_period + 1 : i + 1].min()
        highest_high = high[i - k_period + 1 : i + 1].max()
        if highest_high != lowest_low:
            k[i] = 100 * (close[i] - lowest_low) / (highest_high - lowest_low)
        else:
            k[i] = 50
    d = np.full(n, np.nan)
    for i in range(k_period + d_period - 2, n):
        d[i] = np.nanmean(k[i - d_period + 1 : i + 1])
    return k, d


def cci(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 20) -> np.ndarray:
    """Commodity Channel Index."""
    n = len(close)
    tp = (high + low + close) / 3
    cci_out = np.full(n, np.nan)
    for i in range(period - 1, n):
        sma_tp = tp[i - period + 1 : i + 1].mean()
        mean_dev = np.abs(tp[i - period + 1 : i + 1] - sma_tp).mean()
        if mean_dev != 0:
            cci_out[i] = (tp[i] - sma_tp) / (0.015 * mean_dev)
    return cci_out


def williams_r(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """Williams %R."""
    n = len(close)
    wr = np.full(n, np.nan)
    for i in range(period - 1, n):
        highest_high = high[i - period + 1 : i + 1].max()
        lowest_low = low[i - period + 1 : i + 1].min()
        if highest_high != lowest_low:
            wr[i] = -100 * (highest_high - close[i]) / (highest_high - lowest_low)
        else:
            wr[i] = -50
    return wr


def add_momentum_indicators(df: pl.DataFrame) -> pl.DataFrame:
    close = df["close"].to_numpy().astype(float)
    high = df["high"].to_numpy().astype(float)
    low = df["low"].to_numpy().astype(float)
    
    r = rsi(close, 14)
    k, d = stochastic(high, low, close, 14, 3)
    cci_val = cci(high, low, close, 20)
    wr = williams_r(high, low, close, 14)
    
    return df.with_columns(
        pl.Series("rsi", r),
        pl.Series("stoch_k", k),
        pl.Series("stoch_d", d),
        pl.Series("cci", cci_val),
        pl.Series("williams_r", wr),
    )


def detect_rsi_divergence(df: pl.DataFrame, lookback: int = 40) -> dict:
    """Gelişmiş bullish/bearish divergence tespiti - çoklu swing noktaları."""
    if df.height < 30 or "rsi" not in df.columns:
        return {"bullish_divergence": False, "bearish_divergence": False, "divergence_strength": 0}
    
    close = df["close"].to_numpy()[-lookback:]
    rsi_s = df["rsi"].to_numpy()[-lookback:]
    
    if len(close) < 10 or np.isnan(rsi_s).all():
        return {"bullish_divergence": False, "bearish_divergence": False, "divergence_strength": 0}
    
    # Tüm swing low ve high noktalarını bul
    lows_idx, _ = find_peaks(-close, distance=5, prominence=np.std(close)*0.3)
    highs_idx, _ = find_peaks(close, distance=5, prominence=np.std(close)*0.3)
    
    bullish_score = 0
    bearish_score = 0
    
    # Bullish divergence: fiyat daha düşük dip, RSI daha yüksek dip
    if len(lows_idx) >= 2:
        recent_lows = sorted(lows_idx[-5:])  # son 5 swing low
        for i in range(len(recent_lows) - 1):
            idx1, idx2 = recent_lows[i], recent_lows[i + 1]
            if close[idx2] < close[idx1] and rsi_s[idx2] > rsi_s[idx1] + 3:
                # RSI yükseliyor ama fiyat düşüyor - bullish divergence
                strength = (rsi_s[idx2] - rsi_s[idx1]) / max(1, abs(close[idx2] - close[idx1]) / np.std(close))
                bullish_score = max(bullish_score, min(1.0, strength / 10))
    
    # Bearish divergence: fiyat daha yüksek tepe, RSI daha düşük tepe
    if len(highs_idx) >= 2:
        recent_highs = sorted(highs_idx[-5:])
        for i in range(len(recent_highs) - 1):
            idx1, idx2 = recent_highs[i], recent_highs[i + 1]
            if close[idx2] > close[idx1] and rsi_s[idx2] < rsi_s[idx1] - 3:
                strength = (rsi_s[idx1] - rsi_s[idx2]) / max(1, abs(close[idx2] - close[idx1]) / np.std(close))
                bearish_score = max(bearish_score, min(1.0, strength / 10))
    
    return {
        "bullish_divergence": bullish_score >= 0.4,
        "bearish_divergence": bearish_score >= 0.4,
        "bullish_strength": round(bullish_score, 2),
        "bearish_strength": round(bearish_score, 2),
        "divergence_strength": max(bullish_score, bearish_score),
    }
