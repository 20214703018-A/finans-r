"""Formasyon Yaşı & Sonrası Hareket – çift tepe 48 mum önce ise ne oldu/ ne beklenir?

Deterministik: pattern rightmost index → age bars/hours, post-formation fiyat hareketi, beklenti.
"""
import math, polars as pl
import numpy as np

TIME_MIN = {"15m":15,"1h":60,"4h":240,"1d":1440}

def evaluate_age(df: pl.DataFrame, pattern, timeframe: str) -> dict:
    n = df.height
    if n < 10 or not pattern.indices:
        return {"age_bars": None, "age_label": "bilinmiyor", "freshness": 1.0}
    max_idx = max(pattern.indices.values())
    age_bars = n - 1 - max_idx  # kaç mum geçti
    tf_min = TIME_MIN.get(timeframe, 60)
    age_hours = age_bars * tf_min / 60
    if timeframe == "15m":
        age_label = f"{age_bars} mum (~{age_bars*15}dk / {age_hours:.1f}sa)"
    elif timeframe == "1h":
        age_label = f"{age_bars} mum (~{age_hours:.0f}sa / {age_hours/24:.1f}g)"
    elif timeframe == "4h":
        age_label = f"{age_bars} mum (~{age_hours:.0f}sa / {age_bars*4/24:.1f}g)"
    else:
        age_label = f"{age_bars} mum (~{age_bars}g)"
    # freshness 1.0 → 0.0 (0-15 bar taze, 15-35 orta, >35 bayat)
    if age_bars <= 15:
        freshness = 1.0
        fresh_label = "taze"
    elif age_bars <= 35:
        freshness = 0.6
        fresh_label = "orta"
    elif age_bars <= 60:
        freshness = 0.3
        fresh_label = "bayat"
    else:
        freshness = 0.1
        fresh_label = "çok bayat (geçmiş)"

    # sonrası hareket: oluşumdan bu yana high/low/close değişimi
    closes = df["close"].to_numpy().astype(float)
    highs = df["high"].to_numpy().astype(float)
    lows = df["low"].to_numpy().astype(float)
    post_closes = closes[max_idx+1:] if max_idx+1 < n else np.array([])
    if len(post_closes)==0:
        post_label = "henüz kapanış yok"
        chg = 0; max_fav = 0; max_adv = 0; hit_target = None; hit_stop = None
    else:
        chg = (closes[-1] - closes[max_idx]) / closes[max_idx] * 100
        # pattern yönüne göre fav/adv
        is_bull = pattern.pattern_type in ("double_bottom","inverse_head_shoulders","falling_wedge","ascending_triangle","triangle")
        # ama double_top bearish için fav = düşüş
        is_bear = pattern.pattern_type in ("double_top","head_shoulders","rising_wedge","descending_triangle")
        if is_bear:
            # fav = en düşük
            max_fav = (closes[max_idx] - np.min(lows[max_idx+1:])) / closes[max_idx] * 100 if len(lows[max_idx+1:]) else 0
            max_adv = (np.max(highs[max_idx+1:]) - closes[max_idx]) / closes[max_idx] * 100 if len(highs[max_idx+1:]) else 0
        elif is_bull:
            max_fav = (np.max(highs[max_idx+1:]) - closes[max_idx]) / closes[max_idx] * 100 if len(highs[max_idx+1:]) else 0
            max_adv = (closes[max_idx] - np.min(lows[max_idx+1:])) / closes[max_idx] * 100 if len(lows[max_idx+1:]) else 0
        else:
            max_fav = float(np.max(np.abs(post_closes - closes[max_idx])) / closes[max_idx] * 100) if len(post_closes) else 0
            max_adv = max_fav
        # hedef/stop vuruldu mu?
        tgt = pattern.target; inv = pattern.invalidation
        hit_target = False; hit_stop = False
        if tgt and inv and len(post_closes):
            if is_bull:
                hit_target = bool(np.any(highs[max_idx+1:] >= tgt))
                hit_stop = bool(np.any(lows[max_idx+1:] <= inv))
            elif is_bear:
                hit_target = bool(np.any(lows[max_idx+1:] <= tgt))
                hit_stop = bool(np.any(highs[max_idx+1:] >= inv))
        # etiket
        if hit_target and not hit_stop:
            post_label = f"hedef vurulmuş (+{max_fav:.1f}%) → beklenti: kâr realizasyonu, yeni giriş geç"
        elif hit_stop and not hit_target:
            post_label = f"stop vurulmuş (−{max_adv:.1f}%) → formasyon geçersiz → yeni sinyal bekle"
        elif hit_target and hit_stop:
            post_label = f"hedef ve stop aynı pencerede → volatil, beklenti nötr"
        else:
            # henüz hedefe gitmemiş, ama yön?
            if abs(chg) < 0.6:
                post_label = f"yatay {chg:+.1f}% (max fav {max_fav:.1f}% / adv {max_adv:.1f}%) → beklenti: neckline kırılımı beklenecek"
            elif (is_bull and chg > 0) or (is_bear and chg < 0):
                post_label = f"yönünde ilerledi {chg:+.1f}% (max {max_fav:.1f}%) → beklenti: trend devam, stop altında/üstünde takip"
            else:
                post_label = f"tersine gitti {chg:+.1f}% (adv {max_adv:.1f}%) → beklenti: formasyon zayıflıyor, bayat riski"

    return {
        "age_bars": age_bars,
        "age_hours": round(age_hours,1),
        "age_label": age_label,
        "freshness": freshness,
        "fresh_label": fresh_label,
        "change_since_pct": round(float(chg),2) if 'chg' in locals() else None,
        "max_fav_pct": round(float(max_fav),2) if 'max_fav' in locals() else None,
        "max_adv_pct": round(float(max_adv),2) if 'max_adv' in locals() else None,
        "hit_target": hit_target,
        "hit_stop": hit_stop,
        "post_label": post_label,
        "is_fresh": freshness >= 0.6,
    }
