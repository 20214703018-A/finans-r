"""İşlem Planı – gerçeğe en yakın sinyal için giriş / stop / hedef / geçerlilik (§20-21, §26-27).

Deterministik, sıralı, tüm OHLCV+indikatörler + pattern seviyeleri kullanılır.
Alım kriterleri: breakout + hacim + trend + momentum + S/R + YOLO (hepsi scoring kutuları).
Geçerli: status mature/confirmed ve breakout var + hacim güçlü ise. Geçersiz: invalidation fiyatı aşılırsa.
"""
import math
import polars as pl

BULLISH = {"double_bottom","inverse_head_shoulders","falling_wedge","ascending_triangle","triangle"}
BEARISH = {"double_top","head_shoulders","rising_wedge","descending_triangle"}

def _safe(v, d=0):
    if v is None: return d
    if isinstance(v,float) and (math.isnan(v) or math.isinf(v)): return d
    return float(v)

TIMEFRAME_META = {
    "15m": {"minutes":15, "label":"15 dakika", "hours":0.25, "session":"crypto 24/7 – 15m bar"},
    "1h":  {"minutes":60, "label":"1 saat",    "hours":1,    "session":"crypto 24/7 – 1h bar"},
    "4h":  {"minutes":240,"label":"4 saat",    "hours":4,    "session":"crypto 24/7 – 4h bar"},
    "1d":  {"minutes":1440,"label":"1 gün",    "hours":24,   "session":"crypto 24/7 – 1d bar (BIST 1d ayrı)"},
}

def build_trading_plan(pattern, df: pl.DataFrame, breakout: dict, scores: dict, timeframe: str | None = None) -> dict:
    last = df.row(-1, named=True) if df.height else {}
    close = _safe(last.get("close"), 0)
    atr = _safe(last.get("atr"), close*0.02 if close else 1)
    atr_pct = _safe(last.get("atr_pct"), 50)
    rvol = _safe(last.get("rvol"), 1); rsi = _safe(last.get("rsi"), 50)
    tf = timeframe or (df["timeframe"][0] if "timeframe" in df.columns and df.height else "1h")
    tf_meta = TIMEFRAME_META.get(tf, {"minutes":60,"label":tf,"hours":1})
    tf_min = tf_meta["minutes"]; tf_h = tf_meta["hours"]
    neck = pattern.neckline
    tgt = pattern.target
    inv = pattern.invalidation
    if neck is None or tgt is None or inv is None:
        return {"entry": None, "stop": None, "target": None, "rr": None, "valid": False, "invalid_where": None, "criteria": []}

    is_bull = pattern.pattern_type in BULLISH
    # giriş: neckline ± ATR*0.12 breakout buffer (spec §26)
    entry = neck + atr*0.12 if is_bull else neck - atr*0.12
    stop = inv
    target = tgt

    # RR (deterministik)
    risk = abs(entry - stop) if stop else None
    reward = abs(target - entry) if target and entry else None
    rr = round(reward/risk,2) if risk and risk!=0 and reward else None

    # kriter checklist (hepsi scoring kutularından deterministik eşik)
    geom_ok = _safe(pattern.geometry_score,0) >= 0.65  # §20-21
    breakout_ok = breakout.get("is_breakout") is True and not breakout.get("fake_breakout") and breakout.get("quality") in ("moderate","strong")
    breakout_pending = breakout.get("quality")=="none"  # henüz kırılım yok
    volume_ok = rvol >= 1.2  # §17 strong
    trend_ok = scores.get("trend",0) >= 9  # 15 üzerinden
    mom_ok = scores.get("momentum",0) >= 7 or scores.get("divergence",{}).get("bullish_divergence") or scores.get("divergence",{}).get("bearish_divergence")
    sr_ok = scores.get("support_resistance",0) >= 3
    yolo_ok = scores.get("yolo",0) >= 2  # ≥0.64 conf
    # geçersiz olduğu yer: stop fiyatı
    invalid_where = f"Fiyat {stop:.2f} {'altına' if is_bull else 'üstüne'} (invalidation) kapanış yaparsa" if stop else None
    # geçerli olduğu yer: neckline breakout + yukarıdaki teyitler
    valid = (
        pattern.status in ("mature","breakout_pending","confirmed") and
        (breakout_ok or breakout_pending) and  # mature'da bile kriter listesinde pending göster
        geom_ok
    )
    # sinyale dönüşme eşiği: watch+ (≥70) ve en az 4 kriter yeşil ise gerçeğe yakın
    green = sum([geom_ok, breakout_ok or breakout_pending, volume_ok, trend_ok, mom_ok, sr_ok, yolo_ok])
    is_actionable = valid and scores.get("final",0) >= 70 and green >= 4 and not breakout.get("fake_breakout")

    criteria = [
        {"k":"Geometri (tepe/dip benzerliği)", "ok": geom_ok, "val": f"{_safe(pattern.geometry_score,0):.2f} ≥0.65"},
        {"k":"Breakout", "ok": breakout_ok, "val": f"{breakout.get('quality')} atr={_safe(breakout.get('breakout_strength_atr'),0):.2f} {'✓' if breakout_ok else 'beklemede' if breakout_pending else 'zayıf/fake'}"},
        {"k":"Hacim (RVOL)", "ok": volume_ok, "val": f"{rvol:.2f} {('≥1.2' if volume_ok else '<1.2 strong değil')}"},
        {"k":"Trend (EMA/ADX/Slope)", "ok": trend_ok, "val": f"{scores.get('trend')}/15"},
        {"k":"Momentum (RSI/div)", "ok": mom_ok, "val": f"RSI {rsi:.1f} { 'div var' if mom_ok and (scores.get('divergence',{}).get('bullish_divergence') or scores.get('divergence',{}).get('bearish_divergence')) else ''}"},
        {"k":"S/R confluence", "ok": sr_ok, "val": f"{scores.get('support_resistance')}/5"},
        {"k":"YOLO görsel teyit", "ok": yolo_ok, "val": f"{_safe(scores.get('yolo'),0)}/5"},
    ]

    # — Timeframe'e göre hedef süresi / mum sayısı (deterministik) —
    # pattern yüksekliği / ATR ile tahmini bar sayısı; volatilite ve trend düzeltmesi
    height = abs(tgt - neck) if tgt and neck else 0
    # taban: height / (ATR * k)  k=0.55 → ATR başına ~0.55 hareket, volatiliteye göre ayar
    # trend güçlü ise daha hızlı, zayıf/range ise daha yavaş
    k = 0.55
    if scores.get("trend",0) >= 12:
        k = 0.70  # güçlü trendde hedefe daha hızlı
    elif scores.get("trend",0) <= 5:
        k = 0.45
    est_bars = int(round(height / (atr * k + 1e-12))) if atr and height else 18
    # ATR% yüksekse daha hızlı, düşükse yavaş (volatilite)
    if atr_pct > 70:
        est_bars = max(5, int(est_bars * 0.8))
    elif atr_pct < 30:
        est_bars = int(est_bars * 1.25)
    est_bars = max(4, min(60, est_bars))  # clamp 4-60 bar
    # timeframe'e göre saat/gün çevirimi
    est_hours = est_bars * tf_h
    if tf == "15m":
        dur_label = f"{est_bars} mum (~{est_bars*15}dk / {est_hours:.1f}sa)"
    elif tf == "1h":
        dur_label = f"{est_bars} mum (~{est_hours:.0f} saat / {est_hours/24:.1f} gün)"
    elif tf == "4h":
        dur_label = f"{est_bars} mum (~{est_hours:.0f} saat / {est_bars*4/24:.1f} gün)"
    else:  # 1d
        dur_label = f"{est_bars} mum (~{est_bars} gün)"
    # grafik penceresi: chart 120 mum → grafiğin kaç saat/gün olduğu
    chart_bars = min(df.height, 120)
    chart_hours = chart_bars * tf_h
    chart_label = f"{chart_bars} mum ({chart_hours/24:.1f} gün)" if tf_h>=1 else f"{chart_bars} mum ({chart_bars*tf_min}dk)"
    # geçerlilik penceresi: breakout + est_bars*1.5 veya stop
    valid_bars = max(12, int(est_bars * 1.5))
    valid_hours = valid_bars * tf_h
    if tf == "15m":
        valid_label = f"Breakout + {valid_bars} mum ({valid_bars*15}dk / {valid_hours:.1f}sa) veya stop"
    elif tf == "1h":
        valid_label = f"Breakout + {valid_bars} mum ({valid_hours:.0f}sa / {valid_hours/24:.1f}g) veya stop"
    elif tf == "4h":
        valid_label = f"Breakout + {valid_bars} mum ({valid_hours:.0f}sa / {valid_bars*4/24:.1f}g) veya stop"
    else:
        valid_label = f"Breakout + {valid_bars} mum ({valid_bars}g) veya stop"

    return {
        "direction": "long" if is_bull else "short",
        "timeframe": tf,
        "timeframe_label": tf_meta["label"],
        "timeframe_minutes": tf_min,
        "entry": round(float(entry),2),
        "entry_note": f"neckline {neck:.2f} ± ATR*0.12 ({atr*0.12:.2f}) kapanış teyidi ({tf})",
        "stop": round(float(stop),2) if stop else None,
        "stop_note": f"invalidation {stop:.2f} üstü/altı kapanış → geçersiz",
        "target": round(float(target),2) if target else None,
        "target_note": f"ölçülü hareket: neckline ± height ({height:.2f})",
        "risk": round(float(risk),2) if risk else None,
        "reward": round(float(reward),2) if reward else None,
        "rr": rr,
        "valid": valid,
        "is_actionable": is_actionable,
        "invalid_where": invalid_where,
        "valid_until": valid_label,
        "valid_until_bars": valid_bars,
        "valid_where": f"Fiyat {entry:.2f} {'üzerinde' if is_bull else 'altında'} kapanış ({tf}) + hacim ≥1.2 + YOLO teyit" if is_bull else f"Fiyat {entry:.2f} altında kapanış ({tf})",
        "est_bars": est_bars,
        "est_duration": dur_label,
        "est_hours": round(est_hours,1),
        "chart_window": chart_label,
        "chart_bars": chart_bars,
        "criteria": criteria,
        "green_count": green,
        "status": pattern.status,
        "needs": "Breakout bekleniyor" if breakout_pending else ("Geçersiz (failed/fake)" if pattern.status=="failed" or breakout.get("fake_breakout") else "Teyitli" if breakout_ok else "Zayıf"),
    }
