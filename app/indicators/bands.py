"""Advanced Volatility & Bands Engine - Bollinger Bands, Keltner Channel, Donchian Channel."""
import polars as pl
import numpy as np


def bollinger_bands(close: np.ndarray, period: int = 20, std_dev: float = 2.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bollinger Bands: SMA ± (std_dev * standard deviation)."""
    n = len(close)
    sma = np.full(n, np.nan)
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    
    for i in range(period - 1, n):
        window = close[i - period + 1 : i + 1]
        sma[i] = window.mean()
        std = window.std()
        upper[i] = sma[i] + (std_dev * std)
        lower[i] = sma[i] - (std_dev * std)
    
    return sma, upper, lower


def keltner_channel(high: np.ndarray, low: np.ndarray, close: np.ndarray, ema_period: int = 20, atr_period: int = 10, multiplier: float = 2.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Keltner Channel: EMA ± (multiplier * ATR)."""
    n = len(close)
    
    # EMA hesapla
    alpha = 2 / (ema_period + 1)
    ema = np.empty(n)
    ema[0] = close[0]
    for i in range(1, n):
        ema[i] = alpha * close[i] + (1 - alpha) * ema[i - 1]
    
    # ATR hesapla
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    
    atr = np.full(n, np.nan)
    atr[atr_period - 1] = tr[:atr_period].mean()
    for i in range(atr_period, n):
        atr[i] = (atr[i - 1] * (atr_period - 1) + tr[i]) / atr_period
    
    # Keltner bands
    upper = ema + (multiplier * atr)
    lower = ema - (multiplier * atr)
    
    return ema, upper, lower


def donchian_channel(high: np.ndarray, low: np.ndarray, period: int = 20) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Donchian Channel: Highest high, lowest low, midline."""
    n = len(high)
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    mid = np.full(n, np.nan)
    
    for i in range(period - 1, n):
        upper[i] = high[i - period + 1 : i + 1].max()
        lower[i] = low[i - period + 1 : i + 1].min()
        mid[i] = (upper[i] + lower[i]) / 2
    
    return upper, mid, lower


def add_bands_indicators(df: pl.DataFrame) -> pl.DataFrame:
    """Tüm bant indikatörlerini ekle."""
    close = df["close"].to_numpy().astype(float)
    high = df["high"].to_numpy().astype(float)
    low = df["low"].to_numpy().astype(float)
    
    # Bollinger Bands
    bb_sma, bb_upper, bb_lower = bollinger_bands(close, 20, 2.0)
    bb_width = (bb_upper - bb_lower) / (bb_sma + 1e-12) * 100
    bb_pct = (close - bb_lower) / (bb_upper - bb_lower + 1e-12)  # %B indicator
    
    # Keltner Channel
    kc_mid, kc_upper, kc_lower = keltner_channel(high, low, close, 20, 10, 2.0)
    
    # Donchian Channel
    dc_upper, dc_mid, dc_lower = donchian_channel(high, low, 20)
    
    # Squeeze tespiti: BB içinde KC (volatilite sıkışması)
    squeeze = np.zeros(len(close), dtype=bool)
    for i in range(len(close)):
        if not np.isnan(bb_upper[i]) and not np.isnan(kc_upper[i]):
            squeeze[i] = (bb_upper[i] <= kc_upper[i]) and (bb_lower[i] >= kc_lower[i])
    
    return df.with_columns([
        pl.Series("bb_sma", bb_sma),
        pl.Series("bb_upper", bb_upper),
        pl.Series("bb_lower", bb_lower),
        pl.Series("bb_width", bb_width),
        pl.Series("bb_pct", bb_pct),
        pl.Series("kc_mid", kc_mid),
        pl.Series("kc_upper", kc_upper),
        pl.Series("kc_lower", kc_lower),
        pl.Series("dc_upper", dc_upper),
        pl.Series("dc_mid", dc_mid),
        pl.Series("dc_lower", dc_lower),
        pl.Series("bb_kc_squeeze", squeeze.astype(int)),
    ])


def detect_squeeze_breakout(df: pl.DataFrame) -> dict:
    """Bollinger-Keltner squeeze sonrası breakout tespiti."""
    if df.height < 50 or "bb_kc_squeeze" not in df.columns:
        return {"squeeze_active": False, "breakout": None}
    
    squeeze = df["bb_kc_squeeze"].to_numpy()
    close = df["close"].to_numpy()
    bb_upper = df["bb_upper"].to_numpy()
    bb_lower = df["bb_lower"].to_numpy()
    
    # Son 10 barda squeeze var mı?
    recent_squeeze = squeeze[-10:].sum() > 0
    
    # Squeeze sonrası breakout
    breakout_direction = None
    breakout_bar = None
    
    for i in range(len(squeeze) - 1, max(0, len(squeeze) - 20), -1):
        if i < 10:
            break
        # Önceki barda squeeze vardı, bu barda yok ve fiyat üst bandı aştı
        if squeeze[i-1] and not squeeze[i]:
            if close[i] > bb_upper[i]:
                breakout_direction = "bullish"
                breakout_bar = i
                break
            elif close[i] < bb_lower[i]:
                breakout_direction = "bearish"
                breakout_bar = i
                break
    
    return {
        "squeeze_active": recent_squeeze,
        "squeeze_duration": int(squeeze[-20:].sum()) if len(squeeze) >= 20 else int(squeeze.sum()),
        "breakout": breakout_direction,
        "breakout_bar": breakout_bar,
    }
