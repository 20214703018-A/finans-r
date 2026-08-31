"""Backtesting §41-44 – walk-forward, outcome labels, YOLO ablation."""
import polars as pl
import numpy as np
from dataclasses import dataclass


@dataclass
class BacktestResult:
    pattern_type: str
    total: int
    success: int
    win_rate: float
    avg_return_5: float
    avg_return_10: float
    avg_return_20: float
    expectancy: float
    max_favorable_excursion: float
    max_adverse_excursion: float
    false_positive_rate: float


def _future_return(close: np.ndarray, entry_idx: int, horizon: int) -> float | None:
    if entry_idx + horizon >= len(close):
        return None
    return (close[entry_idx + horizon] - close[entry_idx]) / close[entry_idx]


def evaluate_pattern_outcome(
    df: pl.DataFrame,
    pattern,
    entry: str = "neckline_breakout_close",
) -> dict:
    """
    For historical pattern at its breakout bar, evaluate:
      - success = target_hit_before_stop (invalidation) within 20 bars
      - 5/10/20 bar returns
      - MFE/MAE
    Requires df includes future bars after pattern.
    """
    close = df["close"].to_numpy().astype(float)
    high = df["high"].to_numpy().astype(float)
    low = df["low"].to_numpy().astype(float)
    # Find entry index: first close beyond neckline after pattern formation
    neckline = pattern.neckline
    target = pattern.target
    stop = pattern.invalidation
    if neckline is None or target is None or stop is None:
        return {"success": None, "reason": "missing levels"}

    # Locate rightmost index of pattern
    # pattern.indices contains relevant indexes; entry is after max index
    max_idx = max(pattern.indices.values()) if pattern.indices else 0
    # Find first bar after max_idx where breakout condition holds
    is_bullish = pattern.pattern_type in ("double_bottom", "inverse_head_shoulders", "falling_wedge", "ascending_triangle")
    entry_idx = None
    for i in range(max_idx + 1, len(close)):
        if is_bullish and close[i] > neckline:
            entry_idx = i
            break
        if not is_bullish and close[i] < neckline:
            entry_idx = i
            break
    if entry_idx is None:
        return {"success": None, "reason": "no breakout in history"}

    entry_price = close[entry_idx]
    # Walk next 20 bars for target/stop
    success = None
    mfe = 0.0
    mae = 0.0
    for j in range(entry_idx + 1, min(entry_idx + 21, len(close))):
        if is_bullish:
            # MFE: max high vs entry ; MAE: min low vs entry
            mfe = max(mfe, (high[j] - entry_price) / entry_price)
            mae = min(mae, (low[j] - entry_price) / entry_price)
            hit_target = high[j] >= target
            hit_stop = low[j] <= stop
        else:
            # bearish: target below, stop above
            mfe = max(mfe, (entry_price - low[j]) / entry_price)
            mae = min(mae, (entry_price - high[j]) / entry_price)
            hit_target = low[j] <= target
            hit_stop = high[j] >= stop
        if hit_target and not hit_stop:
            success = True
            break
        if hit_stop and not hit_target:
            success = False
            break
        if hit_target and hit_stop:
            # same bar both hit – ambiguous => treat as failure (conservative)
            success = False
            break
    if success is None:
        # Neither hit within 20 bars => evaluate by return direction
        # Consider success = close 20 bars after entry in favorable direction beyond midpoint
        if entry_idx + 20 < len(close):
            ret20 = (close[entry_idx + 20] - entry_price) / entry_price
            if is_bullish:
                success = ret20 > (target - entry_price) / entry_price * 0.5
            else:
                success = ret20 < (target - entry_price) / entry_price * 0.5
        else:
            success = False

    r5 = _future_return(close, entry_idx, 5)
    r10 = _future_return(close, entry_idx, 10)
    r20 = _future_return(close, entry_idx, 20)

    return {
        "entry_idx": entry_idx,
        "entry_price": float(entry_price),
        "success": bool(success),
        "mfe": float(mfe),
        "mae": float(mae),
        "r5": float(r5) if r5 is not None else None,
        "r10": float(r10) if r10 is not None else None,
        "r20": float(r20) if r20 is not None else None,
        "target": float(target),
        "stop": float(stop),
    }


def aggregate_backtest(outcomes: list[dict]) -> dict:
    if not outcomes:
        return {"total": 0}
    successes = sum(1 for o in outcomes if o.get("success") is True)
    total = len([o for o in outcomes if o.get("success") is not None])
    win_rate = successes / total if total else 0
    r5s = [o["r5"] for o in outcomes if o.get("r5") is not None]
    r10s = [o["r10"] for o in outcomes if o.get("r10") is not None]
    r20s = [o["r20"] for o in outcomes if o.get("r20") is not None]
    mfes = [o["mfe"] for o in outcomes if "mfe" in o]
    maes = [o["mae"] for o in outcomes if "mae" in o]
    avg_r5 = float(np.mean(r5s)) if r5s else 0
    avg_r10 = float(np.mean(r10s)) if r10s else 0
    avg_r20 = float(np.mean(r20s)) if r20s else 0
    expectancy = win_rate * (np.mean(mfes) if mfes else 0) - (1 - win_rate) * abs(np.mean(maes) if maes else 0)
    return {
        "total": total,
        "success": successes,
        "win_rate": round(float(win_rate), 4),
        "avg_return_5": round(float(avg_r5), 4),
        "avg_return_10": round(float(avg_r10), 4),
        "avg_return_20": round(float(avg_r20), 4),
        "expectancy": round(float(expectancy), 4),
        "mfe_mean": round(float(np.mean(mfes)) if mfes else 0, 4),
        "mae_mean": round(float(np.mean(maes)) if maes else 0, 4),
        "false_positive_rate": round(1 - win_rate, 4),
    }


def walk_forward_splits(df: pl.DataFrame, train_years: int = 2, test_years: int = 1):
    """Yield (train_df, test_df) splits for walk-forward. Assumes timestamp sorted."""
    # Simple: split by time quantiles if timestamp not yearly
    n = df.height
    # Example splits: 2022-2023 train / 2024 test etc. For generic, do 60/20 and 80/20
    splits = []
    if n < 100:
        return splits
    # Two splits: 0-60%/60-80% and 0-80%/80-100%
    s1_train = df.slice(0, int(n * 0.6))
    s1_test = df.slice(int(n * 0.6), int(n * 0.2))
    s2_train = df.slice(0, int(n * 0.8))
    s2_test = df.slice(int(n * 0.8), n - int(n * 0.8))
    return [(s1_train, s1_test), (s2_train, s2_test)]
