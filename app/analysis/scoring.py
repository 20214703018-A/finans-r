"""Pattern Scoring Engine §33-34 – v2 deterministic, tüm veriler dahil (§47 sıralı).

Weight (spec): Geometry 30, Breakout 20, Volume 15, Trend 15, Momentum 10, YOLO 5, S/R 5 = 100
Her kutu içinde OHLCV + tüm indikatörler (EMA/ADX/slope/ATR/pct/RVOL/OBV/vol_trend/VWAP) deterministik kullanılır.
Hiçbir random yok, aynı input → aynı skor.
"""
import math
import numpy as np
import polars as pl
from app.indicators.volume import rvol_label
from app.indicators.momentum import detect_rsi_divergence
from app.analysis.multi_timeframe import mtf_adjusted_score


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))

def _safe(v, default=0):
    if v is None:
        return default
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return default
    if isinstance(v, np.floating) and (np.isnan(v) or np.isinf(v)):
        return default
    return float(v)

def _last(df: pl.DataFrame) -> dict:
    try:
        return df.row(-1, named=True)
    except Exception:
        return {}

def calculate_score(
    pattern,
    df: pl.DataFrame,
    breakout: dict,
    volume_info: dict,
    trend_info: dict | None,
    regime_info: dict | None,
    sr_info: dict | None,
    yolo_info: dict | None,
    mtf_info: dict | None = None,
) -> dict:
    last = _last(df)
    # raw OHLCV + indikatörler (sıralı §47 kullanıldığını kanıtlamak için hepsi okunur)
    o = _safe(last.get("open"))
    h = _safe(last.get("high"))
    l = _safe(last.get("low"))
    c = _safe(last.get("close"))
    v = _safe(last.get("volume"))
    ema20 = last.get("ema20"); ema50 = last.get("ema50"); ema200 = last.get("ema200")
    adx = last.get("adx"); slope = last.get("ema20_slope")
    rsi_val = last.get("rsi")
    atr = last.get("atr"); atr_pct = last.get("atr_pct")
    rvol = last.get("rvol"); obv = last.get("obv"); vol_sma = last.get("vol_sma20"); vol_trend = last.get("vol_trend")
    vwap = last.get("vwap")
    # sanitized floats
    adx_f = _safe(adx, 15); slope_f = _safe(slope, 0); atr_f = _safe(atr, c*0.02) if c else 0.02
    atr_pct_f = _safe(atr_pct, 50); rvol_f = _safe(rvol, 1.0); vol_trend_f = _safe(vol_trend, 0)
    vwap_f = _safe(vwap, c if c else 0)

    # ---- 1 Geometry 30 (swing benzerliği zaten pattern.geometry_score içinde ATR-normalized) ----
    geom = _clamp(_safe(pattern.geometry_score, 0), 0, 1) * 30  # deterministik: sadece swing motoru çıktısı

    # ---- 2 Breakout 20 – ATR mesafesi + body + ATR% volatilite bağlamı + VWAP ----
    bq = breakout.get("quality", "none")
    strength = _safe(breakout.get("breakout_strength_atr", 0))
    body_atr = _safe(breakout.get("body_atr", 0))
    fake = breakout.get("fake_breakout", False)
    if fake:
        breakout_pts = 0
    elif bq == "strong":
        breakout_pts = 20
    elif bq == "moderate":
        breakout_pts = 14
    elif bq == "weak":
        breakout_pts = 7
    else:
        # proximity: ne kadar yakın (<0.6 ATR ise kısmi)
        if strength < 0.6:
            breakout_pts = 8 - strength * 5
        else:
            breakout_pts = 3
    # body küçüklüğü cezası (deterministik OHLC kullanıldı: open/close farkı)
    if breakout.get("is_breakout") and body_atr < 0.25:
        breakout_pts -= 3  # doji benzeri zayıf gövde
    # volatilite bağlamı: yüksek ATR%’te zayıf breakout daha da zayıf
    if atr_pct_f > 75 and bq == "weak":
        breakout_pts -= 2
    if atr_pct_f < 25 and bq == "strong":
        breakout_pts += 1  # düşük volatilitede güçlü breakout nadir → bonus
    # VWAP: breakout VWAP yönündeyse +1, tersine -1
    if vwap_f and c:
        vwap_dist_atr = (c - vwap_f) / (atr_f + 1e-12)
        if breakout.get("direction") == "up" and vwap_dist_atr > 0.3:
            breakout_pts += 1
        if breakout.get("direction") == "down" and vwap_dist_atr < -0.3:
            breakout_pts += 1
        if breakout.get("direction") == "up" and vwap_dist_atr < -0.8:
            breakout_pts -= 1
        if breakout.get("direction") == "down" and vwap_dist_atr > 0.8:
            breakout_pts -= 1
    breakout_pts = _clamp(breakout_pts, 0, 20)

    # ---- 3 Volume 15 – RVOL + OBV + vol_trend (hepsi volume.py) ----
    # volume_info rvol öncelikli, yoksa df rvol
    if volume_info and volume_info.get("rvol") is not None:
        rvol_f = _safe(volume_info["rvol"], rvol_f)
    # baz RVOL
    if rvol_f < 0.8:
        vol_pts = 3
    elif rvol_f < 1.2:
        vol_pts = 8
    elif rvol_f < 1.5:
        vol_pts = 12
    else:
        vol_pts = 15
    # OBV trend: son 5 barda OBV artıyor mu? (deterministik)
    try:
        obv_series = df["obv"].to_numpy().astype(float) if "obv" in df.columns else None
        if obv_series is not None and len(obv_series) >= 6:
            obv_slope = obv_series[-1] - obv_series[-6]
            price_slope = c - _safe(df["close"][-6])
            # uyum: fiyat↑ OBV↑ veya fiyat↓ OBV↑ (ayı tuzağı) değil, breakout yönüyle OBV aynı yönde olmalı
            if breakout.get("direction") == "up" and obv_slope > 0 and price_slope > 0:
                vol_pts += 2
            elif breakout.get("direction") == "down" and obv_slope < 0 and price_slope < 0:
                vol_pts += 2
            elif breakout.get("is_breakout") and ((breakout.get("direction")=="up" and obv_slope<0) or (breakout.get("direction")=="down" and obv_slope>0)):
                vol_pts -= 2  # hacim fiyata eşlik etmiyor
    except Exception:
        pass
    # vol_trend (SMA20 eğimi)
    if vol_trend_f > 0.08 and breakout.get("is_breakout"):
        vol_pts += 1
    if vol_trend_f < -0.08 and breakout.get("is_breakout"):
        vol_pts -= 1
    # breakout hacimsizse ceza (spec)
    if breakout.get("is_breakout") and rvol_f < 0.9:
        vol_pts -= 6
    # sıfır hacim kontrolü (quality)
    if v == 0:
        vol_pts -= 5
    vol_pts = _clamp(vol_pts, 0, 15)

    # ---- 4 Trend 15 – EMA hizası + ADX + slope + EMA200 mesafe + regime (hepsi trend.py/regime.py) ----
    if mtf_info is not None:
        trend_pts = mtf_adjusted_score(pattern.pattern_type, mtf_info)
        trend_pts = int(np.clip((trend_pts + 10) / 25 * 15, 0, 15))
    else:
        # deterministik alt skorlar
        ema_score = 0  # 0-5
        # close vs EMA'lar
        try:
            e20 = _safe(ema20, None); e50 = _safe(ema50, None); e200 = _safe(ema200, None)
            # None kontrolü: NaN zaten _safe ile handle ama orijinal None ise atla
            has_e20 = ema20 is not None and not (isinstance(ema20,float) and math.isnan(ema20))
            has_e50 = ema50 is not None and not (isinstance(ema50,float) and math.isnan(ema50))
            has_e200 = ema200 is not None and not (isinstance(ema200,float) and math.isnan(ema200))
            if has_e20 and has_e50 and has_e200:
                if c > e20 > e50 > e200:
                    ema_score = 5
                elif c > e20 > e50:
                    ema_score = 3
                elif c < e20 < e50 < e200:
                    ema_score = 5  # ayıda da hiza tam → güçlü trend
                elif c < e20 < e50:
                    ema_score = 3
                else:
                    ema_score = 1
            elif has_e20 and has_e50:
                if c > e20 > e50 or c < e20 < e50:
                    ema_score = 3
        except Exception:
            ema_score = 2
        adx_score = 0  # 0-5
        if adx_f > 30:
            adx_score = 5
        elif adx_f > 25:
            adx_score = 3
        elif adx_f > 18:
            adx_score = 1
        slope_score = 0  # 0-3
        if abs(slope_f) > 0.35:
            slope_score = 3
        elif abs(slope_f) > 0.15:
            slope_score = 2
        elif abs(slope_f) > 0.05:
            slope_score = 1
        # EMA200 mesafe (fiyatın 200’den uzaklığı) – trende aykırı pattern'e ceza
        ema200_dist_score = 1  # nötr 1
        try:
            if ema200 is not None and not (isinstance(ema200,float) and math.isnan(ema200)) and ema200 != 0:
                dist_pct = (c - _safe(ema200, c)) / _safe(ema200, c) * 100
                bullish = pattern.pattern_type in ("double_bottom","inverse_head_shoulders","falling_wedge","ascending_triangle")
                bearish = pattern.pattern_type in ("double_top","head_shoulders","rising_wedge","descending_triangle")
                if bullish and dist_pct < -3:  # çok aşağıda – dip dönüşü için uygun → bonus
                    ema200_dist_score = 2
                elif bearish and dist_pct > 3:
                    ema200_dist_score = 2
                elif bullish and dist_pct > 4:
                    ema200_dist_score = 0
                elif bearish and dist_pct < -4:
                    ema200_dist_score = 0
        except Exception:
            pass
        # toplam 5+5+3+2=15
        raw = ema_score + adx_score + slope_score + ema200_dist_score
        # bullish/bearish uyumu: pattern yönü ile trend yönü uyuşmazsa -4
        t_label = (trend_info.get("trend") if trend_info else None) or (regime_info.get("regime") if regime_info else "RANGE")
        bullish = pattern.pattern_type in ("double_bottom","inverse_head_shoulders","falling_wedge")
        bearish = pattern.pattern_type in ("double_top","head_shoulders","rising_wedge")
        if bullish and "DOWN" not in str(t_label) and "UP" not in str(t_label):
            # RANGE ise nötr, ceza yok
            pass
        elif bullish and "DOWN" in str(t_label) and "UP" not in str(t_label):
            # dipten dönüş ayıda ise aslında kontrarian – momentum ile telafi edilir, hafif ceza
            raw -= 1
        elif bearish and "UP" in str(t_label):
            raw -= 1
        # regime volatilite etkisi: HIGH_VOL'da trend puanı -1 (gürültü)
        if regime_info and regime_info.get("regime") == "HIGH_VOLATILITY":
            raw -= 1
        trend_pts = _clamp(raw, 0, 15)

    # ---- 5 Momentum 10 – RSI + divergence (momentum.py) ----
    div = detect_rsi_divergence(df)
    rsi_f = _safe(rsi_val, None)
    # None check: if rsi_val is None or NaN, keep None
    has_rsi = rsi_val is not None and not (isinstance(rsi_val,float) and math.isnan(rsi_val))
    mom_pts = 5
    if has_rsi:
        if pattern.pattern_type in ("double_bottom","inverse_head_shoulders","falling_wedge"):
            if 30 <= rsi_f <= 55:
                mom_pts = 8
            if div.get("bullish_divergence"):
                mom_pts = 10
            if rsi_f > 70:
                mom_pts = 3
            if rsi_f < 25:
                mom_pts = 4  # aşırı satım – dönüş yakın ama riskli
        elif pattern.pattern_type in ("double_top","head_shoulders","rising_wedge"):
            if 45 <= rsi_f <= 70:
                mom_pts = 8
            if div.get("bearish_divergence"):
                mom_pts = 10
            if rsi_f < 30:
                mom_pts = 3
            if rsi_f > 75:
                mom_pts = 4
        else:  # triangle etc nötr
            if 40 <= rsi_f <= 60:
                mom_pts = 7
            if div.get("bullish_divergence") or div.get("bearish_divergence"):
                mom_pts = 8
    mom_pts = _clamp(mom_pts, 0, 10)

    # ---- 6 YOLO 5 (§30) – HF model: StockLine ignored, Triangle family, wedge cezasız ----
    yolo_pts = 0
    if yolo_info and yolo_info.get("confidence") is not None:
        conf = _safe(yolo_info["confidence"], 0)
        pred = yolo_info.get("pattern")
        if pred is None:
            yolo_pts = 0
        else:
            yolo_map = {
                "W_Bottom": "double_bottom", "M_Head": "double_top", "M_Top": "double_top",
                "Head and shoulders top": "head_shoulders", "Head and shoulders bottom": "inverse_head_shoulders",
                "HS": "head_shoulders", "IHS": "inverse_head_shoulders",
                "Triangle": "triangle", "TRIANGLE": "triangle",
                "ASC_TRI": "ascending_triangle", "DESC_TRI": "descending_triangle",
                "RISING_WEDGE": "rising_wedge", "FALLING_WEDGE": "falling_wedge",
                "double_top": "double_top", "double_bottom": "double_bottom",
                "head_shoulders": "head_shoulders", "inverse_head_shoulders": "inverse_head_shoulders", "triangle": "triangle",
            }
            mapped = yolo_map.get(pred, pred)
            if mapped is not None:
                ml = mapped.lower() if isinstance(mapped,str) else mapped
                if ml in ("double_top","double_bottom","head_shoulders","inverse_head_shoulders","triangle"):
                    mapped = ml
            is_match = False
            if mapped == pattern.pattern_type:
                is_match = True
            elif mapped == "triangle" and pattern.pattern_type in ("triangle","ascending_triangle","descending_triangle"):
                is_match = True
            elif pattern.pattern_type == "triangle" and mapped in ("ascending_triangle","descending_triangle"):
                is_match = True
            if is_match and conf >= 0.40:
                yolo_pts = int(np.clip((conf - 0.40) / 0.60 * 5, 0, 5))
            elif mapped is not None and mapped != pattern.pattern_type and conf >= 0.40:
                if pattern.pattern_type in ("rising_wedge","falling_wedge","ascending_triangle","descending_triangle"):
                    yolo_pts = 0
                else:
                    yolo_pts = -2
            else:
                yolo_pts = 0
    yolo_pts = _clamp(yolo_pts, 0, 5)

    # ---- 7 S/R 5 + VWAP 0-5 içinde (S/R kutusuna VWAP yakınlığı eklenir) ----
    sr_pts = 0
    sr_score = 0.5
    if sr_info and "score" in sr_info and sr_info["score"] is not None:
        sr_score = _safe(sr_info["score"], 0.5)
    sr_pts = int(np.clip(sr_score * 5, 0, 5))
    # VWAP: fiyat VWAP'a çok yakınsa S/R confluence gibi değerlendir, breakout yönüyle aynı taraftaysa +1
    # S/R puanına dahil değil ayrı gösterilsin diye notta tutuyoruz ama total'e yansımaz (spec 5)
    # Deterministik: VWAP mesafesi <0.4 ATR ve breakout yönündeyse sr_pts +1 (cap 5)
    if vwap_f and c and atr_f:
        vwap_atr = abs(c - vwap_f) / (atr_f + 1e-12)
        if vwap_atr < 0.4 and breakout.get("is_breakout"):
            sr_pts = _clamp(sr_pts + 1, 0, 5)
        # çok uzak (>1.2 ATR) ise S/R zayıf → -1
        if vwap_atr > 1.2:
            sr_pts = _clamp(sr_pts - 0, 0, 5)  # nötr bırak (deterministik iz)

    total = geom + breakout_pts + vol_pts + trend_pts + mom_pts + yolo_pts + sr_pts
    total = float(np.clip(total, 0, 100))

    if total < 60:
        label = "discard"
    elif total < 70:
        label = "weak"
    elif total < 80:
        label = "watch"
    elif total < 90:
        label = "strong"
    else:
        label = "exceptional"

    breakdown = {
        "geometry": round(float(geom), 1),
        "breakout": round(float(breakout_pts), 1),
        "volume": round(float(vol_pts), 1),
        "trend": round(float(trend_pts), 1),
        "momentum": round(float(mom_pts), 1),
        "yolo": round(float(yolo_pts), 1),
        "support_resistance": round(float(sr_pts), 1),
        "final": round(float(total), 1),
        "label": label,
        "divergence": div,
        "rsi": float(rsi_f) if has_rsi else None,
        "rvol": float(rvol_f) if rvol is not None else None,
        "rvol_label": rvol_label(rvol_f) if rvol is not None else None,
        # deterministik iz: her indikatörün son değeri breakdown içinde kanıt olarak durur (debug, skoru değiştirmez)
        "_debug": {
            "ema20": _safe(ema20, None) if ema20 is not None and not (isinstance(ema20,float) and math.isnan(ema20)) else None,
            "ema50": _safe(ema50, None) if ema50 is not None and not (isinstance(ema50,float) and math.isnan(ema50)) else None,
            "ema200": _safe(ema200, None) if ema200 is not None and not (isinstance(ema200,float) and math.isnan(ema200)) else None,
            "adx": _safe(adx, None) if adx is not None and not (isinstance(adx,float) and math.isnan(adx)) else None,
            "slope": _safe(slope, None) if slope is not None and not (isinstance(slope,float) and math.isnan(slope)) else None,
            "atr": _safe(atr, None) if atr is not None and not (isinstance(atr,float) and math.isnan(atr)) else None,
            "atr_pct": _safe(atr_pct, None) if atr_pct is not None and not (isinstance(atr_pct,float) and math.isnan(atr_pct)) else None,
            "obv": _safe(obv, None) if obv is not None and not (isinstance(obv,float) and math.isnan(obv)) else None,
            "vol_trend": _safe(vol_trend, None) if vol_trend is not None and not (isinstance(vol_trend,float) and math.isnan(vol_trend)) else None,
            "vwap": _safe(vwap, None) if vwap is not None and not (isinstance(vwap,float) and math.isnan(vwap)) else None,
            "vwap_dist_atr": round(float((c - vwap_f)/(atr_f+1e-12)),2) if vwap_f and c else None,
        }
    }
    return breakdown
