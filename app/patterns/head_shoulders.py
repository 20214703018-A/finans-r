"""Head & Shoulders §22-23."""
import polars as pl
import numpy as np
from app.patterns.swings import SwingResult
from app.patterns.base import PatternCandidate


def _head_shoulders_core(
    df: pl.DataFrame,
    swings: SwingResult,
    inverse: bool = False,
) -> list[PatternCandidate]:
    highs = swings.highs
    lows = swings.lows
    close = df["close"].to_numpy().astype(float)
    atr = df["atr"].to_numpy().astype(float) if "atr" in df.columns else np.full(len(df), np.nan)

    if inverse:
        # Inverse H&S uses lows as shoulders/head, highs as neckline anchors
        pivots = lows
        necks = highs
        pattern_type = "inverse_head_shoulders"
    else:
        pivots = highs
        necks = lows
        pattern_type = "head_shoulders"

    if len(pivots) < 3 or len(necks) < 2:
        return []

    candidates: list[PatternCandidate] = []
    for i in range(len(pivots) - 2):
        left = pivots[i]
        head = pivots[i + 1]
        right = pivots[i + 2]
        # Need neck points between
        neck1_candidates = [n for n in necks if left.index < n.index < head.index]
        neck2_candidates = [n for n in necks if head.index < n.index < right.index]
        if not neck1_candidates or not neck2_candidates:
            continue
        neck1 = min(neck1_candidates, key=lambda x: x.price) if not inverse else max(neck1_candidates, key=lambda x: x.price)
        neck2 = min(neck2_candidates, key=lambda x: x.price) if not inverse else max(neck2_candidates, key=lambda x: x.price)

        # validity
        if not inverse:
            if not (head.price > left.price and head.price > right.price):
                continue
            shoulder_diff = abs(left.price - right.price)
        else:
            if not (head.price < left.price and head.price < right.price):
                continue
            shoulder_diff = abs(left.price - right.price)

        # shoulder similarity: diff < 1.2 ATR or < 1.5% price
        atr_ref = atr[head.index] if not np.isnan(atr[head.index]) else close[head.index] * 0.02
        if np.isnan(atr_ref):
            atr_ref = close[head.index] * 0.02
        if shoulder_diff > atr_ref * 1.2:
            # allow up to 2% price diff as fallback
            if shoulder_diff / (head.price + 1e-12) > 0.02:
                continue
        # Head prominence: head - shoulders > 0.8 ATR
        if not inverse:
            head_prom = head.price - max(left.price, right.price)
        else:
            head_prom = min(left.price, right.price) - head.price
        if head_prom < atr_ref * 0.8:
            continue
        # Neckline: for classic H&S connect neck1-neck2 (allow slope)
        neckline_at_right = float(np.interp(right.index, [neck1.index, neck2.index], [neck1.price, neck2.price]))
        # Use average of neck points as neckline level for scoring
        neckline = (neck1.price + neck2.price) / 2
        # target
        if not inverse:
            height = head.price - neckline
            target = neckline - height
            invalidation = head.price + atr_ref * 0.3
        else:
            height = neckline - head.price
            target = neckline + height
            invalidation = head.price - atr_ref * 0.3

        # Geometry score
        shoulder_sim = max(0, 1 - shoulder_diff / (atr_ref * 1.5))
        prom_score = min(1, head_prom / (atr_ref * 2))
        neck_slope = abs(neck2.price - neck1.price) / (atr_ref + 1e-12)
        neck_score = max(0, 1 - neck_slope / 2)
        geometry = float(np.clip(0.40 * shoulder_sim + 0.40 * prom_score + 0.20 * neck_score, 0, 1))

        # Status by breakout
        status = "mature"
        closes_after = close[right.index + 1 :]
        if len(closes_after) > 0:
            if not inverse:
                # bearish breakdown below neckline
                broke = None
                for k, c in enumerate(closes_after):
                    if c < neckline - atr_ref * 0.12:
                        broke = right.index + 1 + k
                        break
                if broke is not None:
                    reentered = any(close[j] > neckline for j in range(broke + 1, min(broke + 4, len(close))))
                    status = "failed" if reentered else "confirmed"
                else:
                    if close[-1] < neckline + atr_ref * 0.6:
                        status = "breakout_pending"
            else:
                broke = None
                for k, c in enumerate(closes_after):
                    if c > neckline + atr_ref * 0.12:
                        broke = right.index + 1 + k
                        break
                if broke is not None:
                    reentered = any(close[j] < neckline for j in range(broke + 1, min(broke + 4, len(close))))
                    status = "failed" if reentered else "confirmed"
                else:
                    if close[-1] > neckline - atr_ref * 0.6:
                        status = "breakout_pending"
        if geometry < 0.45:
            status = "forming"

        indices = {"left": left.index, "neck1": neck1.index, "head": head.index, "neck2": neck2.index, "right": right.index}
        prices = {"left": left.price, "neck1": neck1.price, "head": head.price, "neck2": neck2.price, "right": right.price}
        candidates.append(
            PatternCandidate(
                pattern_type=pattern_type,
                status=status,
                geometry_score=geometry,
                indices=indices,
                prices=prices,
                neckline=float(neckline),
                invalidation=float(invalidation),
                target=float(target),
                notes=[f"shoulder_diff={shoulder_diff:.2f} head_prom={head_prom:.2f} ATR={atr_ref:.2f}"],
            )
        )
    candidates.sort(key=lambda x: x.geometry_score, reverse=True)
    return candidates[:5]


def detect_head_shoulders(df: pl.DataFrame, swings: SwingResult) -> list[PatternCandidate]:
    return _head_shoulders_core(df, swings, inverse=False)


def detect_inverse_head_shoulders(df: pl.DataFrame, swings: SwingResult) -> list[PatternCandidate]:
    return _head_shoulders_core(df, swings, inverse=True)
