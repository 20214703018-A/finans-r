"""Support / Resistance Engine §19 – ATR-distance clustering (DBSCAN optional)."""
import polars as pl
import numpy as np
from app.patterns.swings import SwingResult


def evaluate_sr(df: pl.DataFrame, pattern, swings: SwingResult) -> dict:
    """
    Cluster swing highs/lows into zones using ATR distance.
    Returns proximity of pattern's key level to nearest zone.
    """
    atr = df["atr"].to_numpy().astype(float) if "atr" in df.columns else np.full(len(df), np.nan)
    atr_ref = float(np.nanmean(atr[-20:])) if np.any(~np.isnan(atr)) else df["close"].to_numpy()[-1] * 0.02
    if np.isnan(atr_ref) or atr_ref == 0:
        atr_ref = df["close"].to_numpy()[-1] * 0.02

    # Gather swing prices
    highs = np.array([h.price for h in swings.highs], dtype=float) if swings.highs else np.array([])
    lows = np.array([l.price for l in swings.lows], dtype=float) if swings.lows else np.array([])
    all_prices = np.concatenate([highs, lows]) if len(highs) or len(lows) else np.array([])

    if len(all_prices) < 3:
        return {"zones": [], "nearest_distance_atr": None, "confluence": 0, "score": 0.5}

    # Simple 1D clustering: sort, group if within 0.6*ATR
    sorted_prices = np.sort(all_prices)
    zones: list[dict] = []
    current = [sorted_prices[0]]
    for p in sorted_prices[1:]:
        if abs(p - np.mean(current)) < atr_ref * 0.6:
            current.append(p)
        else:
            zones.append({"center": float(np.mean(current)), "count": len(current), "low": float(min(current)), "high": float(max(current))})
            current = [p]
    zones.append({"center": float(np.mean(current)), "count": len(current), "low": float(min(current)), "high": float(max(current))})
    # sort by count descending
    zones.sort(key=lambda z: z["count"], reverse=True)

    # Distance from pattern neckline/boundary to nearest zone
    level = pattern.neckline
    if pattern.pattern_type in ("triangle", "ascending_triangle", "descending_triangle", "rising_wedge", "falling_wedge"):
        # use mid of bands
        level = (pattern.prices.get("upper_at_last", level) + pattern.prices.get("lower_at_last", level)) / 2 if level is None else level

    nearest_dist = None
    confluence = 0
    if level is not None and zones:
        dists = [abs(z["center"] - level) for z in zones]
        nearest_dist = min(dists)
        nearest_zone = zones[int(np.argmin(dists))]
        confluence = nearest_zone["count"]
        nearest_atr = nearest_dist / (atr_ref + 1e-12)
    else:
        nearest_atr = None

    # Score: if pattern boundary aligns with strong zone (high confluence, close distance) -> higher score
    # Strong confluence + near distance => supportive
    score = 0.5
    if nearest_atr is not None:
        dist_score = max(0, 1 - nearest_atr / 1.2)  # within 1.2 ATR is good
        conf_score = min(1, confluence / 4)  # 4 touches is strong
        score = float(np.clip(0.6 * dist_score + 0.4 * conf_score, 0, 1))
    return {
        "zones": zones[:5],
        "nearest_distance_atr": float(nearest_atr) if nearest_atr is not None else None,
        "confluence": int(confluence),
        "score": float(score),
        "atr": float(atr_ref),
    }
