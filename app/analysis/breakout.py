"""Breakout Engine §26-27."""
import polars as pl
import numpy as np


def evaluate_breakout(df: pl.DataFrame, pattern) -> dict:
    """
    Returns breakout dict with strength, quality, fake flag.
    Supports double_top/bottom/head_shoulders (neckline) and triangle/wedge (upper/lower bands).
    """
    close = df["close"].to_numpy().astype(float)
    high = df["high"].to_numpy().astype(float)
    low = df["low"].to_numpy().astype(float)
    volume = df["volume"].to_numpy().astype(float) if "volume" in df.columns else np.zeros(len(close))
    atr = df["atr"].to_numpy().astype(float) if "atr" in df.columns else np.full(len(close), np.nan)
    last_idx = len(close) - 1
    atr_last = atr[last_idx] if not np.isnan(atr[last_idx]) else np.nanmean(atr[~np.isnan(atr)]) if np.any(~np.isnan(atr)) else close[last_idx] * 0.02
    if np.isnan(atr_last) or atr_last == 0:
        atr_last = close[last_idx] * 0.02

    # Determine breakout boundary
    neckline = pattern.neckline
    # For triangle/wedge, upper/lower stored in breakout or prices
    upper = None
    lower = None
    if pattern.breakout and "upper" in pattern.breakout:
        upper = pattern.breakout["upper"]
        lower = pattern.breakout["lower"]
        # recompute current trendline value at last bar (already upper/lower)
    elif pattern.pattern_type in ("triangle", "ascending_triangle", "descending_triangle", "rising_wedge", "falling_wedge"):
        upper = pattern.prices.get("upper_at_last")
        lower = pattern.prices.get("lower_at_last")

    close_last = close[last_idx]
    body = abs(close[last_idx] - float(df["open"][last_idx]))
    atr_ratio_body = body / (atr_last + 1e-12)

    result = {
        "atr": float(atr_last),
        "close": float(close_last),
        "body_atr": float(atr_ratio_body),
        "breakout_strength_atr": 0.0,
        "direction": None,
        "is_breakout": False,
        "quality": "none",
        "fake_breakout": False,
    }

    # Double top/bottom / H&S logic
    if pattern.pattern_type in ("double_top", "head_shoulders"):
        # bearish breakdown below neckline
        strength = (neckline - close_last) / (atr_last + 1e-12) if neckline else 0
        # positive means breakdown (close below neckline)
        result["breakout_strength_atr"] = float(strength)
        result["direction"] = "down"
        if close_last < neckline - atr_last * 0.12:
            result["is_breakout"] = True
            if strength < 0.25:
                result["quality"] = "weak"
            elif strength < 0.5:
                result["quality"] = "moderate"
            else:
                result["quality"] = "strong"
            # body quality
            if atr_ratio_body < 0.3:
                result["quality"] = "weak"
        # fake check: next 1-3 bars re-enter (we only have up to last bar; if breakout happened earlier, check last 3 closes)
        # Find breakout bar index
        if result["is_breakout"]:
            # search for first breakout bar index
            broke_idx = None
            for i in range(len(close)):
                if close[i] < neckline - atr_last * 0.12:
                    broke_idx = i
                    break
            if broke_idx is not None and broke_idx + 3 < len(close):
                if any(close[j] > neckline for j in range(broke_idx + 1, min(broke_idx + 4, len(close)))):
                    result["fake_breakout"] = True
                    result["quality"] = "failed"

    elif pattern.pattern_type in ("double_bottom", "inverse_head_shoulders"):
        strength = (close_last - neckline) / (atr_last + 1e-12) if neckline else 0
        result["breakout_strength_atr"] = float(strength)
        result["direction"] = "up"
        if close_last > neckline + atr_last * 0.12:
            result["is_breakout"] = True
            if strength < 0.25:
                result["quality"] = "weak"
            elif strength < 0.5:
                result["quality"] = "moderate"
            else:
                result["quality"] = "strong"
            if atr_ratio_body < 0.3:
                result["quality"] = "weak"
        if result["is_breakout"]:
            broke_idx = None
            for i in range(len(close)):
                if close[i] > neckline + atr_last * 0.12:
                    broke_idx = i
                    break
            if broke_idx is not None and broke_idx + 3 < len(close):
                if any(close[j] < neckline for j in range(broke_idx + 1, min(broke_idx + 4, len(close)))):
                    result["fake_breakout"] = True
                    result["quality"] = "failed"

    elif pattern.pattern_type in ("triangle", "ascending_triangle", "descending_triangle", "rising_wedge", "falling_wedge"):
        if upper is not None and lower is not None:
            # Check which side broke
            if close_last > upper + atr_last * 0.10:
                strength = (close_last - upper) / (atr_last + 1e-12)
                result["breakout_strength_atr"] = float(strength)
                result["direction"] = "up"
                result["is_breakout"] = True
                result["quality"] = "weak" if strength < 0.25 else "moderate" if strength < 0.5 else "strong"
            elif close_last < lower - atr_last * 0.10:
                strength = (lower - close_last) / (atr_last + 1e-12)
                result["breakout_strength_atr"] = float(strength)
                result["direction"] = "down"
                result["is_breakout"] = True
                result["quality"] = "weak" if strength < 0.25 else "moderate" if strength < 0.5 else "strong"
            else:
                # no breakout, but measure proximity
                dist_up = (upper - close_last) / (atr_last + 1e-12)
                dist_down = (close_last - lower) / (atr_last + 1e-12)
                result["breakout_strength_atr"] = float(min(dist_up, dist_down))
                result["quality"] = "none"
            # fake check
            if result["is_breakout"]:
                # if breakout bar then next bars re-enter
                # find breakout idx
                broke_idx = None
                h_slope = pattern.breakout.get("h_slope") if pattern.breakout else None
                l_slope = pattern.breakout.get("l_slope") if pattern.breakout else None
                h_inter = pattern.breakout.get("h_inter") if pattern.breakout else None
                l_inter = pattern.breakout.get("l_inter") if pattern.breakout else None
                for i in range(len(close)):
                    up_i = h_slope * i + h_inter if h_slope is not None else upper
                    lo_i = l_slope * i + l_inter if l_slope is not None else lower
                    if close[i] > up_i + atr_last * 0.10 or close[i] < lo_i - atr_last * 0.10:
                        broke_idx = i
                        break
                if broke_idx is not None and broke_idx + 3 < len(close):
                    # check re-entry
                    went_up = close[broke_idx] > (h_slope * broke_idx + h_inter if h_slope is not None else upper)
                    for j in range(broke_idx + 1, min(broke_idx + 4, len(close))):
                        up_j = h_slope * j + h_inter if h_slope is not None else upper
                        lo_j = l_slope * j + l_inter if l_slope is not None else lower
                        if went_up and close[j] < up_j:
                            result["fake_breakout"] = True
                            result["quality"] = "failed"
                            break
                        if not went_up and close[j] > lo_j:
                            result["fake_breakout"] = True
                            result["quality"] = "failed"
                            break

    # volume confirmation will be merged externally, but attach for scoring
    return result
