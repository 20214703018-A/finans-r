"""Double Top/Bottom §20-21."""
import polars as pl
import numpy as np
from app.patterns.swings import SwingResult
from app.patterns.base import PatternCandidate


def detect_double_top(
    df: pl.DataFrame,
    swings: SwingResult,
    atr_col: str = "atr",
) -> list[PatternCandidate]:
    highs = swings.highs
    lows = swings.lows
    if len(highs) < 2 or len(lows) < 1:
        return []
    close = df["close"].to_numpy().astype(float)
    atr = df[atr_col].to_numpy().astype(float) if atr_col in df.columns else np.full(len(df), np.nan)
    candidates: list[PatternCandidate] = []

    for i in range(len(highs) - 1):
        p1 = highs[i]
        p2 = highs[i + 1]
        # need a valley between p1 and p2
        valleys = [l for l in lows if p1.index < l.index < p2.index]
        if not valleys:
            continue
        valley = min(valleys, key=lambda x: x.price)  # deepest
        # ATR thresholds
        atr_ref = atr[p2.index] if not np.isnan(atr[p2.index]) else atr[~np.isnan(atr)].mean() if np.any(~np.isnan(atr)) else close[p2.index] * 0.02
        if np.isnan(atr_ref):
            atr_ref = close[p2.index] * 0.02

        peak_diff = abs(p1.price - p2.price)
        if peak_diff > atr_ref * 0.75:
            continue
        valley_depth = min(p1.price, p2.price) - valley.price
        if valley_depth < atr_ref * 1.0:
            continue
        # Must not be too far apart (>60 bars) nor too close (<5)
        bar_dist = p2.index - p1.index
        if bar_dist < 5 or bar_dist > 80:
            continue

        neckline = valley.price
        # Target = neckline - pattern height (p avg - neckline)
        height = (p1.price + p2.price) / 2 - neckline
        target = neckline - height
        invalidation = max(p1.price, p2.price) + atr_ref * 0.5

        # Geometry score 0-1
        # peak similarity: 1 - diff/(0.75 ATR)  ; valley depth ratio
        peak_score = max(0, 1 - peak_diff / (atr_ref * 0.75))
        depth_score = min(1, valley_depth / (atr_ref * 1.5))
        # distance score: ideal ~15-30 bars
        dist_score = 1 - min(1, abs(bar_dist - 22) / 30)
        geometry = float(np.clip(0.45 * peak_score + 0.35 * depth_score + 0.20 * dist_score, 0, 1))

        # Determine status by breakout
        # Look at closes after p2
        status = "mature"
        closes_after = close[p2.index + 1 :]
        if len(closes_after) > 0:
            # breakout = close below neckline
            broke_idx = None
            for k, c in enumerate(closes_after):
                if c < neckline - atr_ref * 0.10:  # small buffer
                    broke_idx = p2.index + 1 + k
                    break
            if broke_idx is not None:
                # check fake breakout (re-entry within 3 bars)
                reentered = False
                for j in range(broke_idx + 1, min(broke_idx + 4, len(close))):
                    if close[j] > neckline:
                        reentered = True
                        break
                if reentered:
                    status = "failed"
                else:
                    # Need to see if close stays below with confirmation
                    status = "confirmed"
            else:
                # is price approaching neckline from above?
                last_close = close[-1]
                if last_close < neckline + atr_ref * 0.5:
                    status = "breakout_pending"
                else:
                    status = "mature"
        # weak formation if geometry < 0.5
        if geometry < 0.45:
            status = "forming"

        candidates.append(
            PatternCandidate(
                pattern_type="double_top",
                status=status,
                geometry_score=geometry,
                indices={"peak1": p1.index, "valley": valley.index, "peak2": p2.index},
                prices={"peak1": p1.price, "valley": valley.price, "peak2": p2.price},
                neckline=float(neckline),
                invalidation=float(invalidation),
                target=float(target),
                breakout={},
                notes=[f"peak_diff={peak_diff:.2f} ATR={atr_ref:.2f} bar_dist={bar_dist}"],
            )
        )
    # Keep best by geometry
    candidates.sort(key=lambda x: x.geometry_score, reverse=True)
    return candidates[:5]


def detect_double_bottom(
    df: pl.DataFrame,
    swings: SwingResult,
    atr_col: str = "atr",
) -> list[PatternCandidate]:
    lows = swings.lows
    highs = swings.highs
    if len(lows) < 2 or len(highs) < 1:
        return []
    close = df["close"].to_numpy().astype(float)
    atr = df[atr_col].to_numpy().astype(float) if atr_col in df.columns else np.full(len(df), np.nan)
    candidates: list[PatternCandidate] = []
    for i in range(len(lows) - 1):
        t1 = lows[i]
        t2 = lows[i + 1]
        peaks = [h for h in highs if t1.index < h.index < t2.index]
        if not peaks:
            continue
        peak = max(peaks, key=lambda x: x.price)
        atr_ref = atr[t2.index] if not np.isnan(atr[t2.index]) else close[t2.index] * 0.02
        if np.isnan(atr_ref):
            atr_ref = close[t2.index] * 0.02
        trough_diff = abs(t1.price - t2.price)
        if trough_diff > atr_ref * 0.75:
            continue
        peak_height = peak.price - min(t1.price, t2.price)
        if peak_height < atr_ref * 1.0:
            continue
        bar_dist = t2.index - t1.index
        if bar_dist < 5 or bar_dist > 80:
            continue
        neckline = peak.price
        height = neckline - (t1.price + t2.price) / 2
        target = neckline + height
        invalidation = min(t1.price, t2.price) - atr_ref * 0.5

        trough_score = max(0, 1 - trough_diff / (atr_ref * 0.75))
        height_score = min(1, peak_height / (atr_ref * 1.5))
        dist_score = 1 - min(1, abs(bar_dist - 22) / 30)
        geometry = float(np.clip(0.45 * trough_score + 0.35 * height_score + 0.20 * dist_score, 0, 1))

        status = "mature"
        closes_after = close[t2.index + 1 :]
        if len(closes_after) > 0:
            broke_idx = None
            for k, c in enumerate(closes_after):
                if c > neckline + atr_ref * 0.10:
                    broke_idx = t2.index + 1 + k
                    break
            if broke_idx is not None:
                reentered = False
                for j in range(broke_idx + 1, min(broke_idx + 4, len(close))):
                    if close[j] < neckline:
                        reentered = True
                        break
                status = "failed" if reentered else "confirmed"
            else:
                last_close = close[-1]
                if last_close > neckline - atr_ref * 0.5:
                    status = "breakout_pending"
        if geometry < 0.45:
            status = "forming"

        candidates.append(
            PatternCandidate(
                pattern_type="double_bottom",
                status=status,
                geometry_score=geometry,
                indices={"trough1": t1.index, "peak": peak.index, "trough2": t2.index},
                prices={"trough1": t1.price, "peak": peak.price, "trough2": t2.price},
                neckline=float(neckline),
                invalidation=float(invalidation),
                target=float(target),
                notes=[f"trough_diff={trough_diff:.2f} ATR={atr_ref:.2f} bar_dist={bar_dist}"],
            )
        )
    candidates.sort(key=lambda x: x.geometry_score, reverse=True)
    return candidates[:5]
