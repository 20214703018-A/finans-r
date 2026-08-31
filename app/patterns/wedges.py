"""Wedge Engine §25."""
import polars as pl
import numpy as np
from app.patterns.swings import SwingResult
from app.patterns.base import PatternCandidate


def _fit(x, y):
    if len(x) < 2:
        return 0.0, y[0] if len(y) else 0.0, 1e9
    s, inter = np.polyfit(x, y, 1)
    resid = np.mean((y - (s * x + inter)) ** 2)
    return float(s), float(inter), float(resid)


def detect_wedges(df: pl.DataFrame, swings: SwingResult) -> list[PatternCandidate]:
    highs = swings.highs
    lows = swings.lows
    if len(highs) < 2 or len(lows) < 2:
        return []
    close = df["close"].to_numpy().astype(float)
    atr = df["atr"].to_numpy().astype(float) if "atr" in df.columns else np.full(len(df), np.nan)
    atr_ref = float(np.nanmean(atr[-20:])) if np.any(~np.isnan(atr)) else close[-1] * 0.02
    if np.isnan(atr_ref) or atr_ref == 0:
        atr_ref = close[-1] * 0.02
    n = len(df)
    window_start = max(0, n - 80)
    recent_highs = [h for h in highs if h.index >= window_start]
    recent_lows = [l for l in lows if l.index >= window_start]
    if len(recent_highs) < 2 or len(recent_lows) < 2:
        return []

    hx = np.array([h.index for h in recent_highs], dtype=float)
    hy = np.array([h.price for h in recent_highs], dtype=float)
    lx = np.array([l.index for l in recent_lows], dtype=float)
    ly = np.array([l.price for l in recent_lows], dtype=float)

    h_slope, h_inter, h_resid = _fit(hx, hy)
    l_slope, l_inter, l_resid = _fit(lx, ly)

    price_scale = close[-1]
    h_slope_n = h_slope / price_scale
    l_slope_n = l_slope / price_scale

    pattern_type = None
    # Rising wedge: both slopes >0, h_slope < l_slope (converging upward), both positive
    # Falling wedge: both slopes <0, h_slope < l_slope but l more negative? Actually both negative but h less negative (upper less steep down) -> converging
    # Spec §25:
    # Rising: higher highs + higher lows, lines converge
    # Falling: lower highs + lower lows, lines converge
    # Converge means h_slope < l_slope (upper rising slower than lower, or upper falling faster than lower? Let's reason)
    # For rising wedge, both >0 but h_slope < l_slope would mean lower rises faster -> converge upward (correct)
    # For falling wedge, both <0 and h_slope < l_slope? Example h -0.02, l -0.05 -> h > l (since -0.02 > -0.05) not <. So for falling, need h_slope < l_slope still? -0.05 < -0.02, so lower (-0.05) more negative. Then upper -0.02 > lower -0.05, not converge (they diverge). So falling wedge condition is opposite: h_slope > l_slope also? Let's derive convergence condition universally: h_slope < l_slope means upper slope < lower slope. For falling wedge: upper sloping down shallow (-0.01), lower sloping down steep (-0.03): -0.01 > -0.03, so h > l, which violates h<l. So falling wedge converging requires h_slope > l_slope? Check intersection: h_slope*x + h_inter = l_slope*x + l_inter -> x = (l_inter-h_inter)/(h_slope-l_slope). For apex ahead, need denominator sign matching. Simpler: compute apex and check ahead; wedge should converge regardless of which slope larger, just need apex in future and both slopes same sign.

    # Check same sign
    same_sign = (h_slope > 0 and l_slope > 0) or (h_slope < 0 and l_slope < 0)
    if not same_sign:
        return []
    # Apex ahead check
    denom = h_slope - l_slope
    if abs(denom) < 1e-12:
        return []
    apex_x = (l_inter - h_inter) / denom
    apex_ahead = apex_x - n
    # Both rising -> rising wedge ; both falling -> falling wedge
    if h_slope > 0 and l_slope > 0:
        pattern_type = "rising_wedge"
        # rising wedge converging: l_slope > h_slope (lower steeper)
        if not (l_slope > h_slope):
            return []
        if apex_ahead < 0 or apex_ahead > 80:
            # still possible but weak
            pass
    elif h_slope < 0 and l_slope < 0:
        pattern_type = "falling_wedge"
        # falling wedge converging: h_slope < ??? Actually upper falling slower (less negative) than lower: h -1, l -3 -> -1 > -3, so h > l. So condition is h_slope > l_slope
        if not (h_slope > l_slope):
            return []
        if apex_ahead < 0 or apex_ahead > 80:
            pass
    else:
        return []

    # Residual fit
    resid_score = max(0, 1 - (h_resid + l_resid) / (2 * (atr_ref ** 2) + 1e-12))
    resid_score = float(np.clip(resid_score, 0, 1))
    apex_score = 1 - min(1, abs(apex_ahead - 20) / 40) if 0 <= apex_ahead <= 80 else 0.4
    geometry = float(np.clip(0.55 * resid_score + 0.45 * apex_score, 0, 1))
    if geometry < 0.40:
        return []

    upper_at_last = h_slope * (n - 1) + h_inter
    lower_at_last = l_slope * (n - 1) + l_inter
    height = upper_at_last - lower_at_last
    last_close = close[-1]
    status = "mature"
    broke_up = last_close > upper_at_last + atr_ref * 0.10
    broke_down = last_close < lower_at_last - atr_ref * 0.10
    if broke_up or broke_down:
        status = "confirmed"
    else:
        dist = min(upper_at_last - last_close, last_close - lower_at_last) / (atr_ref + 1e-12)
        if dist < 0.7:
            status = "breakout_pending"

    target_up = upper_at_last + height
    target_down = lower_at_last - height

    c = PatternCandidate(
        pattern_type=pattern_type,
        status=status,
        geometry_score=geometry,
        indices={"h_start": int(recent_highs[0].index), "h_end": int(recent_highs[-1].index), "l_start": int(recent_lows[0].index), "l_end": int(recent_lows[-1].index)},
        prices={"upper_at_last": float(upper_at_last), "lower_at_last": float(lower_at_last), "height": float(height)},
        neckline=float(upper_at_last if broke_up else lower_at_last if broke_down else (upper_at_last + lower_at_last) / 2),
        invalidation=float(lower_at_last - atr_ref if pattern_type == "rising_wedge" else upper_at_last + atr_ref),
        target=float(target_down if pattern_type == "rising_wedge" else target_up),
        notes=[f"h_slope={h_slope:.4f} l_slope={l_slope:.4f} apex_ahead={apex_ahead:.1f}"],
    )
    c.breakout = {"h_slope": h_slope, "l_slope": l_slope, "h_inter": h_inter, "l_inter": l_inter, "upper": upper_at_last, "lower": lower_at_last, "apex_x": float(apex_x)}
    return [c]
