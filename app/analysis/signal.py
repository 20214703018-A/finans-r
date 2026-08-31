"""Gösterge Sinyali Motoru – formasyon yoksa bile MACD+RSI+ADX+RVOL+VWAP birlikte fırsat üretir.

Deterministik: aynı df → aynı sinyal. Threshold'lar sabit.
Skor 0-100, label aynı pipeline ile uyumlu.
"""
import math, polars as pl
import numpy as np
from app.indicators.momentum import detect_rsi_divergence
from app.indicators.volume import rvol_label
from app.indicators.macd import macd_state

def _safe(v, d=None):
    if v is None: return d
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)): return d
    return float(v)

def indicator_signal(df: pl.DataFrame) -> dict | None:
    if df.height < 50:
        return None
    last = df.row(-1, named=True)
    close = _safe(last.get("close"), 0)
    ema20 = _safe(last.get("ema20")); ema50 = _safe(last.get("ema50")); ema200 = _safe(last.get("ema200"))
    adx = _safe(last.get("adx"), 0); slope = _safe(last.get("ema20_slope"), 0)
    rsi = _safe(last.get("rsi"), 50); macd = _safe(last.get("macd")); sig = _safe(last.get("macd_signal")); hist = _safe(last.get("macd_hist"))
    atr = _safe(last.get("atr"), close*0.02); rvol = _safe(last.get("rvol"), 1); vwap = _safe(last.get("vwap"))
    div = detect_rsi_divergence(df)
    # hist trend son 3 bar
    hist_trend = None
    try:
        h = df["macd_hist"].tail(5).to_numpy().astype(float)
        if len(h)>=3 and not np.isnan(h).any():
            if h[-1] > h[-2] > h[-3] and h[-1] > 0:
                hist_trend = "bullish_güçleniyor"
            elif h[-1] < h[-2] < h[-3] and h[-1] < 0:
                hist_trend = "bearish_güçleniyor"
    except Exception:
        pass

    # skor bileşenleri deterministik
    pts = 0
    reasons = []
    direction = None  # long/short

    # 1 trend (EMA hizası + ADX)
    bullish_trend = close > _safe(ema20, close) > _safe(ema50, close) if ema20 and ema50 else False
    bearish_trend = close < _safe(ema20, close) < _safe(ema50, close) if ema20 and ema50 else False
    if bullish_trend and adx > 25 and slope > 0.05:
        pts += 25; reasons.append(f"Güçlü yükseliş trendi EMA>ADX{slope:.2f}")
        direction = "long"
    elif bearish_trend and adx > 25 and slope < -0.05:
        pts += 25; reasons.append(f"Güçlü düşüş trendi ADX {adx:.0f}")
        direction = "short"
    elif adx > 20 and abs(slope) > 0.15:
        pts += 12; reasons.append(f"Trend var ADX {adx:.0f}")

    # 2 RSI + divergence
    if rsi is not None:
        if 30 <= rsi <= 38 and div.get("bullish_divergence"):
            pts += 20; reasons.append(f"RSI bullish divergence {rsi:.1f}"); direction = direction or "long"
        elif 62 <= rsi <= 70 and div.get("bearish_divergence"):
            pts += 20; reasons.append(f"RSI bearish divergence {rsi:.1f}"); direction = direction or "short"
        elif rsi < 32:
            pts += 12; reasons.append(f"RSI aşırı satım {rsi:.1f}"); direction = direction or "long"
        elif rsi > 68:
            pts += 12; reasons.append(f"RSI aşırı alım {rsi:.1f}"); direction = direction or "short"

    # 3 MACD
    ms = macd_state(last)
    if ms["signal"] == "bullish" and hist is not None and hist > 0 and hist_trend == "bullish_güçleniyor":
        pts += 25; reasons.append(f"MACD bullish cross hist {hist:.3f}"); direction = direction or "long"
    elif ms["signal"] == "bearish" and hist is not None and hist < 0 and hist_trend == "bearish_güçleniyor":
        pts += 25; reasons.append(f"MACD bearish cross hist {hist:.3f}"); direction = direction or "short"
    elif ms["signal"] != "nötr":
        pts += 8; reasons.append(f"MACD {ms['signal']}")

    # 4 hacim
    if rvol >= 1.5:
        pts += 10; reasons.append(f"RVOL very_strong {rvol:.2f}")
    elif rvol >= 1.0:
        pts += 4; reasons.append(f"RVOL {rvol:.2f}")

    # 5 VWAP
    if vwap and close:
        dist_atr = (close - vwap) / (atr + 1e-12)
        if abs(dist_atr) < 0.3:
            pts += 5; reasons.append(f"VWAP yakın {dist_atr:.2f} ATR")
        elif abs(dist_atr) > 1.5:
            pts -= 5; reasons.append(f"VWAP uzak {dist_atr:.2f} ATR")

    score = int(np.clip(pts, 0, 100))
    # sadece güçlü sinyaller fırsat sayılsın: ≥60 ve en az 3 bileşen + yön belli
    if score < 60 or direction is None or len([r for r in reasons if "Trend" in r or "MACD" in r or "RSI" in r]) < 2:
        return None
    label = "watch" if score < 70 else "strong" if score < 85 else "exceptional"
    return {
        "pattern_type": "indicator_signal",
        "direction": direction,
        "score": score,
        "label": label,
        "reasons": reasons,
        "rsi": rsi, "macd": macd, "macd_signal": sig, "macd_hist": hist, "hist_trend": hist_trend,
        "adx": adx, "slope": slope, "rvol": rvol, "rvol_label": rvol_label(rvol),
        "divergence": div, "macd_state": ms,
    }
