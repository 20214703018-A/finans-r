"""Triangle Engine §24."""
import polars as pl
import numpy as np
from app.patterns.swings import SwingResult
from app.patterns.base import PatternCandidate


def _linear_fit(x: np.ndarray, y: np.ndarray):
    if len(x) < 2:
        return 0.0, y[0] if len(y) else 0.0, 1e9
    slope, intercept = np.polyfit(x, y, 1)
    y_pred = slope * x + intercept
    resid = np.mean((y - y_pred) ** 2)
    return float(slope), float(intercept), float(resid)


def detect_triangles(df: pl.DataFrame, swings: SwingResult) -> list[PatternCandidate]:
    highs = swings.highs
    lows = swings.lows
    if len(highs) < 2 or len(lows) < 2:
        return []
    close = df["close"].to_numpy().astype(float)
    atr = df["atr"].to_numpy().astype(float) if "atr" in df.columns else np.full(len(df), np.nan)
    atr_ref = float(np.nanmean(atr[-20:])) if np.any(~np.isnan(atr)) else close[-1] * 0.02
    if np.isnan(atr_ref) or atr_ref == 0:
        atr_ref = close[-1] * 0.02

    # Need at least 2 upper swing highs descending/flat and 2 lower swing lows ascending/flat
    # Use last ~60 bars window for relevance
    # Collect candidate windows: take last 4 highs/lows in recent range
    candidates: list[PatternCandidate] = []
    # We try a single window: last 60 bars
    n = len(df)
    window_start = max(0, n - 80)
    recent_highs = [h for h in highs if h.index >= window_start]
    recent_lows = [l for l in lows if l.index >= window_start]
    if len(recent_highs) < 2 or len(recent_lows) < 2:
        return []

    # Fit trendlines
    hx = np.array([h.index for h in recent_highs], dtype=float)
    hy = np.array([h.price for h in recent_highs], dtype=float)
    lx = np.array([l.index for l in recent_lows], dtype=float)
    ly = np.array([l.price for l in recent_lows], dtype=float)

    h_slope, h_inter, h_resid = _linear_fit(hx, hy)
    l_slope, l_inter, l_resid = _linear_fit(lx, ly)

    # Normalize slopes by price scale (price per bar / price)
    price_scale = close[-1]
    h_slope_n = h_slope / price_scale
    l_slope_n = l_slope / price_scale

    # Classify
    # Horizontal threshold: slope within ±0.02% per bar
    horiz = 0.0002  # 0.02% per bar
    is_h_high = abs(h_slope_n) < horiz
    is_h_low = abs(l_slope_n) < horiz

    pattern_type = None
    if h_slope_n < -horiz and l_slope_n > horiz:
        pattern_type = "triangle"  # symmetrical
    elif is_h_high and l_slope_n > horiz:
        pattern_type = "ascending_triangle"
    elif h_slope_n < -horiz and is_h_low:
        pattern_type = "descending_triangle"
    else:
        # No triangle
        return []

    # Convergence check: lines should converge (upper slope < lower slope)
    if h_slope >= l_slope:
        # not converging
        return []

    # Geometry score: based on residuals (tight fit) and slopes magnitudes balanced
    # resid normalized by ATR
    resid_score = max(0, 1 - (h_resid + l_resid) / (2 * (atr_ref ** 2) + 1e-12))
    resid_score = float(np.clip(resid_score, 0, 1))
    # slopes: for sym triangle expect |h_slope| ~ |l_slope|
    if pattern_type == "triangle":
        sym_score = 1 - min(1, abs(abs(h_slope_n) - abs(l_slope_n)) / (abs(h_slope_n) + abs(l_slope_n) + 1e-9))
    else:
        sym_score = 0.7  # not applicable
    convergence_score = max(0, 1 - (h_slope - l_slope) / (abs(h_slope) + abs(l_slope) + price_scale * 0.001))
    # Actually simpler: convergence good if h_slope <0 and l_slope >0 and they approach
    # Use apex distance
    # Apex where lines intersect: solve h_slope*x + h_inter = l_slope*x + l_inter
    denom = h_slope - l_slope
    if abs(denom) < 1e-12:
        return []
    apex_x = (l_inter - h_inter) / denom
    # apex should be in future but not too far (within ~40 bars ahead)
    apex_ahead = apex_x - n
    if apex_ahead < -10 or apex_ahead > 60:
        apex_score = 0.3
    else:
        apex_score = 1 - min(1, abs(apex_ahead - 15) / 30)

    geometry = float(np.clip(0.45 * resid_score + 0.25 * sym_score + 0.30 * apex_score, 0, 1))
    if geometry < 0.40:
        return []

    # Neckline/target: breakout levels are the two trendlines at current bar
    upper_at_last = h_slope * (n - 1) + h_inter
    lower_at_last = l_slope * (n - 1) + l_inter
    # For scoring boundaries
    last_close = close[-1]
    # Status: if close breaks outside with volume, confirmed; else mature/breakout_pending
    status = "mature"
    broke_up = last_close > upper_at_last + atr_ref * 0.12
    broke_down = last_close < lower_at_last - atr_ref * 0.12
    if broke_up or broke_down:
        # check fake breakout next bars (need at least 1 bar after)
        status = "confirmed"
        # Note: true fake detection requires post-breakout bars; will be re-evaluated in breakout engine
        if abs(last_close - (upper_at_last if broke_up else lower_at_last)) < atr_ref * 0.10:
            status = "breakout_pending"
    else:
        # near boundary?
        dist_up = (upper_at_last - last_close) / (atr_ref + 1e-12)
        dist_down = (last_close - lower_at_last) / (atr_ref + 1e-12)
        if min(dist_up, dist_down) < 0.6:
            status = "breakout_pending"

    height = upper_at_last - lower_at_last
    target_up = upper_at_last + height
    target_down = lower_at_last - height

    candidates.append(
        PatternCandidate(
            pattern_type=pattern_type,
            status=status,
            geometry_score=geometry,
            indices={"h_start": int(recent_highs[0].index), "h_end": int(recent_highs[-1].index), "l_start": int(recent_lows[0].index), "l_end": int(recent_lows[-1].index)},
            prices={"upper_at_last": float(upper_at_last), "lower_at_last": float(lower_at_last), "height": float(height)},
            neckline=float(upper_at_last if broke_up else lower_at_last if broke_down else (upper_at_last + lower_at_last) / 2),
            invalidation=float(lower_at_last - atr_ref if broke_up else upper_at_last + atr_ref if broke_down else lower_at_last),
            target=float(target_up if broke_up or not broke_down else target_down),
            notes=[
                f"h_slope={h_slope:.4f} l_slope={l_slope:.4f} apex_ahead={apex_ahead:.1f} resid={h_resid:.2f}/{l_resid:.2f}"
            ],
        )
    )
    # stash slopes for breakout engine
    for c in candidates:
        c.breakout = {"h_slope": h_slope, "l_slope": l_slope, "h_inter": h_inter, "l_inter": l_inter, "upper": upper_at_last, "lower": lower_at_last, "apex_x": float(apex_x)}
    return candidates
