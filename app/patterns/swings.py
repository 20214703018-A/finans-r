"""Swing Engine §12-13 – SciPy peaks + ATR-adaptive ZigZag."""
from dataclasses import dataclass
import polars as pl
import numpy as np
from scipy.signal import find_peaks


@dataclass
class SwingPoint:
    index: int
    timestamp: object
    price: float
    kind: str  # "high" | "low"


@dataclass
class SwingResult:
    highs: list[SwingPoint]
    lows: list[SwingPoint]
    all_sorted: list[SwingPoint]


def _atr_threshold(atr_series: np.ndarray, idx: int, multiplier: float = 1.5) -> float:
    v = atr_series[idx]
    if np.isnan(v) or v == 0:
        return float("inf")  # forces fallback to raw peaks
    return v * multiplier


def detect_swings(df: pl.DataFrame, atr_col: str = "atr", atr_multiplier: float = 1.5, peak_distance: int = 3) -> SwingResult:
    """
    1) find_peaks for highs/lows on high/low arrays
    2) ATR-adaptive filter: successive swings must differ by >= ATR*1.5
       Otherwise keep more extreme.
    """
    high = df["high"].to_numpy().astype(float)
    low = df["low"].to_numpy().astype(float)
    close = df["close"].to_numpy().astype(float)
    timestamps = df["timestamp"].to_list()
    atr = df[atr_col].to_numpy().astype(float) if atr_col in df.columns else np.full(len(df), np.nan)

    # Use high for peaks, low for troughs
    # distance ensures swings not too close
    peaks_idx, _ = find_peaks(high, distance=peak_distance)
    troughs_idx, _ = find_peaks(-low, distance=peak_distance)

    # Convert to SwingPoints
    raw_highs = [SwingPoint(int(i), timestamps[i], float(high[i]), "high") for i in peaks_idx]
    raw_lows = [SwingPoint(int(i), timestamps[i], float(low[i]), "low") for i in troughs_idx]

    # ATR adaptive filtering – only merge very close swings in BOTH price and time.
    # For pattern detection like Double Top where two peaks have similar price (<0.75*ATR)
    # but are separated in time and have a meaningful valley between, we must keep both.
    # Hence: merge iff price diff < thresh AND bar distance < 10
    def filter_by_atr(points: list[SwingPoint], is_high: bool) -> list[SwingPoint]:
        if not points:
            return points
        filtered: list[SwingPoint] = [points[0]]
        for p in points[1:]:
            prev = filtered[-1]
            thresh = _atr_threshold(atr, p.index, atr_multiplier)
            if thresh == float("inf"):
                filtered.append(p)
                continue
            diff = abs(p.price - prev.price)
            bar_dist = p.index - prev.index
            # Only suppress if both price close AND time close
            if diff < thresh and bar_dist < 10:
                if is_high:
                    if p.price > prev.price:
                        filtered[-1] = p
                else:
                    if p.price < prev.price:
                        filtered[-1] = p
            else:
                filtered.append(p)
        return filtered

    highs = filter_by_atr(sorted(raw_highs, key=lambda x: x.index), is_high=True)
    lows = filter_by_atr(sorted(raw_lows, key=lambda x: x.index), is_high=False)

    all_sorted = sorted(highs + lows, key=lambda x: x.index)
    return SwingResult(highs=highs, lows=lows, all_sorted=all_sorted)


def zigzag_swings(df: pl.DataFrame, atr_col: str = "atr", atr_multiplier: float = 1.5) -> list[SwingPoint]:
    """Alternative ATR ZigZag – follows §13 state machine (for ablation)."""
    high = df["high"].to_numpy().astype(float)
    low = df["low"].to_numpy().astype(float)
    timestamps = df["timestamp"].to_list()
    atr = df[atr_col].to_numpy().astype(float) if atr_col in df.columns else np.full(len(df), np.nan)
    if len(df) < 2:
        return []
    # Start with first close as pivot
    swings: list[SwingPoint] = []
    trend = 0  # 1 up, -1 down, 0 unknown
    pivot_idx = 0
    pivot_price = float(df["close"][0])

    for i in range(1, len(df)):
        thresh = _atr_threshold(atr, i, atr_multiplier)
        if np.isinf(thresh):
            continue
        cur_high = high[i]
        cur_low = low[i]
        if trend >= 0:  # looking for up continuation or reversal to down
            # track highest
            if cur_high > pivot_price + thresh and trend == 0:
                trend = 1
                pivot_idx = i
                pivot_price = cur_high
            elif trend == 1 and cur_high > pivot_price:
                pivot_idx = i
                pivot_price = cur_high
            elif trend == 1 and cur_low < pivot_price - thresh:
                # reversal
                swings.append(SwingPoint(pivot_idx, timestamps[pivot_idx], pivot_price, "high"))
                trend = -1
                pivot_idx = i
                pivot_price = cur_low
        if trend <= 0:
            if cur_low < pivot_price - thresh and trend == 0:
                trend = -1
                pivot_idx = i
                pivot_price = cur_low
            elif trend == -1 and cur_low < pivot_price:
                pivot_idx = i
                pivot_price = cur_low
            elif trend == -1 and cur_high > pivot_price + thresh:
                swings.append(SwingPoint(pivot_idx, timestamps[pivot_idx], pivot_price, "low"))
                trend = 1
                pivot_idx = i
                pivot_price = cur_high
    # append last pivot
    if trend == 1:
        swings.append(SwingPoint(pivot_idx, timestamps[pivot_idx], pivot_price, "high"))
    elif trend == -1:
        swings.append(SwingPoint(pivot_idx, timestamps[pivot_idx], pivot_price, "low"))
    return sorted(swings, key=lambda x: x.index)
