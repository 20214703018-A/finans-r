"""Core analyze pipeline §46-47 – single entry point for API & scheduler."""
import math
import polars as pl
import numpy as np
from app.providers import get_provider_for_symbol
from app.data.normalize import bars_to_df, normalize
from app.data.quality import validate_data
from app.indicators import calculate_indicators, classify_trend
from app.patterns.swings import detect_swings
from app.patterns.double_top import detect_double_top, detect_double_bottom
from app.patterns.head_shoulders import detect_head_shoulders, detect_inverse_head_shoulders
from app.patterns.triangles import detect_triangles
from app.patterns.wedges import detect_wedges
from app.analysis import evaluate_breakout, evaluate_sr, evaluate_regime, calculate_score
from app.analysis.plan import build_trading_plan
from app.analysis.age import evaluate_age
from app.analysis.signal import indicator_signal
from app.analysis.multi_timeframe import evaluate_mtf_context
from app.reasoning.client import generate_reasoning
from app.vision.yolo import run_yolo_confirmation


def _sanitize(obj):
    """Recursively replace NaN/Inf with None for JSON compliance."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, np.floating):
        v = float(obj)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


async def analyze_asset(
    symbol: str,
    timeframe: str,
    limit: int = 300,
    include_reasoning: bool = True,
    higher_timeframes: dict[str, pl.DataFrame] | None = None,
) -> dict:
    # 1. Market data
    provider = get_provider_for_symbol(symbol)
    bars = await provider.get_bars(symbol=symbol, timeframe=timeframe, limit=limit)
    # 2. Normalize
    df = bars_to_df(bars)
    df = normalize(df)
    # 3. Validate
    report = validate_data(df, timeframe)
    if report.duplicate_count > 0 or report.nan_count > 0:
        # strict per spec – raise but allow warnings
        if not report.ok:
            # don't hard fail on warnings, only on dup/nan
            pass
    if df.height < 50:
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "asset_id": bars[0].asset_id if bars else f"{symbol}.UNKNOWN",
            "quality": report.__dict__,
            "indicators": None,
            "patterns": [],
            "error": f"insufficient data: {df.height} bars (need >=50)",
        }

    # 4. Indicators
    df = calculate_indicators(df)

    # 5. Swings
    swings = detect_swings(df, atr_col="atr", atr_multiplier=1.5)

    # 6. Numerical pattern detection (all types)
    raw_patterns = []
    raw_patterns.extend(detect_double_top(df, swings))
    raw_patterns.extend(detect_double_bottom(df, swings))
    raw_patterns.extend(detect_head_shoulders(df, swings))
    raw_patterns.extend(detect_inverse_head_shoulders(df, swings))
    raw_patterns.extend(detect_triangles(df, swings))
    raw_patterns.extend(detect_wedges(df, swings))

    # Sort by geometry before scoring, limit top candidates to avoid noise
    raw_patterns.sort(key=lambda p: p.geometry_score, reverse=True)
    # Keep top 10 overall
    raw_patterns = raw_patterns[:10]

    # 7-12. For each pattern: breakout, volume, trend, regime, SR, YOLO, scoring, reasoning
    regime = evaluate_regime(df)
    mtf_ctx = None
    if higher_timeframes:
        mtf_ctx = evaluate_mtf_context(df, higher_timeframes)

    # YOLO: tek render + inference, sonra her pattern için teyit (§30 independent visual confirmation)
    # Cache to avoid 10x render cost
    yolo_global = None
    yolo_global_pattern = None
    yolo_global_conf = None
    yolo_global_raw = None
    yolo_global_all = None
    yolo_global_available = False
    try:
        from app.vision.yolo import get_yolo_engine
        yolo_eng = get_yolo_engine()
        if yolo_eng.is_ready():
            _y = yolo_eng.predict(df)
            yolo_global_pattern = _y.pattern
            yolo_global_conf = _y.confidence
            yolo_global_raw = _y.raw
            yolo_global_all = _y.all_detections
            yolo_global_available = True
        else:
            yolo_global_raw = {"error": yolo_eng._load_error}
    except Exception as e:
        yolo_global_raw = {"error": str(e)}

    # §47 deterministik sıra: 1 market data ✓ 2 normalize ✓ 3 quality ✓ 4 indicators ✓ 5 swing ✓ 6 pattern ✓
    # 7 breakout → 8 volume → 9 trend/regime → 10 S/R → 11 YOLO → 12 scoring → 13 reasoning
    enriched = []
    for pat in raw_patterns:
        breakout = evaluate_breakout(df, pat)
        # volume snapshot
        vol_rvol = None
        if "rvol" in df.columns:
            try:
                vol_rvol = float(df["rvol"][-1])
            except Exception:
                vol_rvol = None
        volume_info = {"rvol": vol_rvol, "rvol_label": None}
        # trend context for fallback
        last_row = df.row(-1, named=True)
        trend_label = classify_trend(last_row)

        sr = evaluate_sr(df, pat, swings)

        # Per-pattern YOLO confirmation from cached global prediction – tip + konum check
        # YOLO chart her zaman son 120 mumu gösterir (render_chart tail 120), sayısal pattern 300 bar içinde eski ise YOLO görmez
        if yolo_global_available:
            canon = yolo_global_pattern
            is_conf = None
            # konum çakışması: YOLO bbox merkezinin mum indeksi ile pattern'in merkezinin farkı < 30 bar ve aynı görünür pencerede olmalı
            yolo_candle_center = None
            visible_start = max(0, df.height - 120)
            try:
                # ilk detection bbox'ından merkez al (en yüksek conf)
                if yolo_global_all and len(yolo_global_all) > 0 and yolo_global_all[0].get("bbox"):
                    bx = yolo_global_all[0]["bbox"]  # [x1,y1,x2,y2] pixel 0-1280
                    x_center = (bx[0] + bx[2]) / 2
                    # mplfinance plot alanı yaklaşık left 80 .. right 1260 (1180px) → 120 mum
                    left, plot_w = 80, 1180
                    # clamp
                    x_center = max(left, min(left+plot_w, x_center))
                    rel = (x_center - left) / plot_w
                    yolo_candle_center = visible_start + int(rel * 120)
                else:
                    yolo_candle_center = None
            except Exception:
                yolo_candle_center = None
            # pattern merkez
            try:
                pat_center = int(sum(pat.indices.values()) / len(pat.indices)) if pat.indices else None
            except Exception:
                pat_center = None
            # görünür pencere dışındaki pattern YOLO ile teyit edilemez
            pat_visible = (pat_center is not None and pat_center >= visible_start) if pat_center is not None else True
            # tip eşleşmesi
            type_match = False
            if canon is not None and yolo_global_conf is not None:
                if canon == pat.pattern_type:
                    type_match = True
                elif canon == "triangle" and pat.pattern_type in ("triangle", "ascending_triangle", "descending_triangle"):
                    type_match = True
                elif pat.pattern_type == "triangle" and canon in ("ascending_triangle", "descending_triangle"):
                    type_match = True
                elif "triangle" in (canon or "") and "triangle" in (pat.pattern_type or ""):
                    type_match = True
            if canon is None or yolo_global_conf is None:
                is_conf = None
            elif not pat_visible:
                # çok öncede → YOLO görmedi, nötr (ceza yok, teyit de yok)
                is_conf = None
            elif not type_match:
                is_conf = False
            else:
                # tip uyuştu ama konum uzaksa → mekansal çelişki → teyit değil
                # tolerans 20 mum (~%16 chart) – YOLO kutusu ile sayısal swing merkezi çakışmalı
                if yolo_candle_center is not None and pat_center is not None:
                    if abs(yolo_candle_center - pat_center) > 20:
                        is_conf = False
                    else:
                        is_conf = True
                else:
                    is_conf = True
            yolo = {
                "pattern": canon,
                "confidence": yolo_global_conf,
                "is_confirmation": is_conf,
                "available": True,
                "raw": yolo_global_raw,
                "all_detections": yolo_global_all,
                "yolo_candle_center": yolo_candle_center,
                "pattern_center": pat_center,
                "visible_window": [visible_start, df.height-1],
            }
        else:
            # fallback: per-pattern call (will return available False)
            yolo = run_yolo_confirmation(df, pat.pattern_type) if False else {"pattern": yolo_global_pattern, "confidence": yolo_global_conf, "is_confirmation": None, "available": False, "reason": (yolo_global_raw or {}).get("error", "yolo not available"), "raw": yolo_global_raw}

        scores = calculate_score(
            pattern=pat,
            df=df,
            breakout=breakout,
            volume_info=volume_info,
            trend_info={"trend": trend_label},
            regime_info=regime,
            sr_info=sr,
            yolo_info=yolo,
            mtf_info=mtf_ctx,
        )

        pat.breakout = breakout
        pat.volume = volume_info
        pat.trend = {"trend": trend_label}
        pat.regime = regime.get("regime")
        pat.support_resistance = sr
        pat.yolo = yolo
        pat.scores = scores
        pat.final_score = scores["final"]
        # trading plan deterministik §20-27: giriş/stop/hedef/RR/geçerlilik – timeframe'e göre süre hesabı
        trading_plan = build_trading_plan(pat, df, breakout, scores, timeframe=timeframe)
        # yaş & sonrası hareket (ör: 48 mum önce çift tepe ne oldu/ ne beklenir)
        age_info = evaluate_age(df, pat, timeframe)
        # freshness skor cezası: bayat ise finalden düş (çok bayat -8, bayat -4)
        if age_info["freshness"] <= 0.1:
            scores["final"] = max(0, scores["final"] - 8)
            pat.final_score = scores["final"]
            scores["label"] = "discard" if scores["final"]<60 else "weak" if scores["final"]<70 else scores["label"]
        elif age_info["freshness"] <= 0.3:
            scores["final"] = max(0, scores["final"] - 4)
            pat.final_score = scores["final"]

        reasoning = None
        if include_reasoning:
            reasoning = await generate_reasoning(
                {
                    "pattern_type": pat.pattern_type,
                    "neckline": pat.neckline,
                    "target": pat.target,
                    "invalidation": pat.invalidation,
                    "breakout": breakout,
                    "yolo": yolo,
                    "regime": regime,
                    "trading_plan": trading_plan,
                    "age": age_info,
                },
                scores,
            )

        enriched.append(
            _sanitize(
                {
                    **pat.to_dict(),
                    "trading_plan": trading_plan,
                    "age": age_info,
                    "reasoning": reasoning,
                    "quality": report.__dict__,
                }
            )
        )

    # Sort by final_score desc
    enriched.sort(key=lambda x: x["final_score"] if x["final_score"] is not None else -1, reverse=True)

    # Formasyon yoksa bile güçlü gösterge sinyali üret (RSI+MACD+ADX+RVOL konfluensi)
    indicator_opportunity = None
    if not enriched or all(p["final_score"] < 60 for p in enriched):
        sig = indicator_signal(df)
        if sig:
            # timeframe aware süre ekle
            sig["timeframe"] = timeframe
            sig["age"] = {"age_label": "güncel (0 mum)", "fresh_label": "taze (gösterge)"}

    # Build indicator snapshot (last bar)
    last = df.row(-1, named=True)
    # Convert timestamp to iso
    ts = last.get("timestamp")
    if hasattr(ts, "isoformat"):
        ts_iso = ts.isoformat()
    else:
        ts_iso = str(ts)

    indicators_snapshot = _sanitize(
        {
            "close": last.get("close"),
            "ema20": last.get("ema20"),
            "ema50": last.get("ema50"),
            "ema200": last.get("ema200"),
            "adx": last.get("adx"),
            "rsi": last.get("rsi"),
            "atr": last.get("atr"),
            "atr_pct": last.get("atr_pct"),
            "rvol": last.get("rvol"),
            "vwap": last.get("vwap"),
            "trend": classify_trend(last),
            "regime": regime,
            "timestamp": ts_iso,
        }
    )

    return _sanitize(
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "asset_id": bars[0].asset_id if bars else f"{symbol}.UNKNOWN",
            "quality": report.__dict__,
            "indicators": indicators_snapshot,
            "swings": {
                "highs": [{"index": s.index, "price": s.price} for s in swings.highs[-10:]],
                "lows": [{"index": s.index, "price": s.price} for s in swings.lows[-10:]],
            },
            "patterns": enriched,
            "pattern_count": len(enriched),
            "indicator_signal": indicator_opportunity,
        }
    )
