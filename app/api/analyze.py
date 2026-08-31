from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from app.api.schemas import AnalyzeRequest, ScanRequest
from app.pipeline import analyze_asset
import asyncio

router = APIRouter(tags=["analyze"])


@router.post("/analyze")
async def analyze(req: AnalyzeRequest):
    try:
        result = await analyze_asset(
            symbol=req.symbol,
            timeframe=req.timeframe,
            limit=req.limit,
            include_reasoning=req.include_reasoning,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        # Kraken/network errors
        raise HTTPException(status_code=502, detail=f"analyze failed: {e}")


@router.post("/scan")
async def scan(req: ScanRequest):
    if len(req.symbols) > 20:
        raise HTTPException(status_code=400, detail="max 20 symbols per scan")
    # Run concurrently with semaphore to avoid rate limits
    sem = asyncio.Semaphore(4)

    async def _one(sym: str):
        async with sem:
            try:
                res = await analyze_asset(sym, req.timeframe, limit=req.limit, include_reasoning=False)
                # deterministik filtre: default watch+ (≥70) unless include_weak
                thr = req.min_score if not req.include_weak else min(req.min_score, 60)
                patterns = [p for p in res.get("patterns", []) if p.get("final_score", 0) >= thr]
                return {"symbol": sym, "asset_id": res.get("asset_id"), "patterns": patterns, "pattern_count": len(patterns), "indicators": res.get("indicators"), "quality": res.get("quality"), "error": res.get("error")}
            except Exception as e:
                return {"symbol": sym, "error": str(e), "patterns": []}

    results = await asyncio.gather(*[_one(s) for s in req.symbols])
    # Rank all patterns across symbols by final_score
    all_patterns = []
    for r in results:
        for p in r.get("patterns", []):
            all_patterns.append({"symbol": r["symbol"], **p})
    all_patterns.sort(key=lambda x: x.get("final_score", 0), reverse=True)

    return {
        "timeframe": req.timeframe,
        "results": results,
        "ranked": all_patterns,
        "total_patterns": len(all_patterns),
    }


@router.post("/backtest")
async def backtest_endpoint(req: AnalyzeRequest, lookback: int = 1000):
    """Lightweight backtest proxy – re-runs analyze with larger limit and evaluates outcomes.
    For true 1000+ historical pattern test use app/analysis/backtest.py directly.
    """
    from app.providers import get_provider_for_symbol
    from app.data.normalize import bars_to_df, normalize
    from app.indicators import calculate_indicators
    from app.patterns.swings import detect_swings
    from app.patterns.double_top import detect_double_top, detect_double_bottom
    from app.patterns.head_shoulders import detect_head_shoulders, detect_inverse_head_shoulders
    from app.patterns.triangles import detect_triangles
    from app.patterns.wedges import detect_wedges
    from app.analysis.backtest import evaluate_pattern_outcome, aggregate_backtest
    from app.data.quality import validate_data

    provider = get_provider_for_symbol(req.symbol)
    bars = await provider.get_bars(req.symbol, req.timeframe, limit=lookback)
    import polars as pl

    df = normalize(bars_to_df(bars))
    if df.height < 80:
        raise HTTPException(status_code=400, detail="insufficient data for backtest")
    df = calculate_indicators(df)
    swings = detect_swings(df)
    pats = []
    pats.extend(detect_double_top(df, swings))
    pats.extend(detect_double_bottom(df, swings))
    pats.extend(detect_head_shoulders(df, swings))
    pats.extend(detect_inverse_head_shoulders(df, swings))
    pats.extend(detect_triangles(df, swings))
    pats.extend(detect_wedges(df, swings))
    outcomes = [evaluate_pattern_outcome(df, p) for p in pats]
    # filter valid
    outcomes = [o for o in outcomes if o.get("success") is not None]
    agg = aggregate_backtest(outcomes)
    return {"symbol": req.symbol, "timeframe": req.timeframe, "patterns_found": len(pats), "evaluated": len(outcomes), "aggregate": agg, "outcomes": outcomes[:20]}


@router.get("/chart")
async def chart_png(
    symbol: str = Query(..., examples=["BTCUSD"]),
    timeframe: str = Query(..., examples=["1h"]),
    limit: int = Query(120, ge=20, le=500),
):
    """1280x720 chart PNG (§31) – YOLO'nun gördüğü görüntüyle birebir aynı."""
    from app.providers import get_provider_for_symbol
    from app.data.normalize import bars_to_df, normalize
    from app.indicators import calculate_indicators
    from app.vision.chart import render_chart

    try:
        provider = get_provider_for_symbol(symbol)
        bars = await provider.get_bars(symbol, timeframe, limit=limit)
        df = normalize(bars_to_df(bars))
        df = calculate_indicators(df)
        png = render_chart(df, candles=120)
        return Response(content=png, media_type="image/png", headers={"Cache-Control": "no-cache"})
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"chart failed: {e}")


@router.get("/yolo/preview")
async def yolo_preview(
    symbol: str = Query(..., examples=["BTCUSD"]),
    timeframe: str = Query(..., examples=["1h"]),
    limit: int = Query(120, ge=20, le=500),
):
    """Yalnız YOLO – chart + HF model sonucu (tek hisse YOLO test)."""
    from app.providers import get_provider_for_symbol
    from app.data.normalize import bars_to_df, normalize
    from app.indicators import calculate_indicators
    from app.vision.yolo import get_yolo_engine

    provider = get_provider_for_symbol(symbol)
    bars = await provider.get_bars(symbol, timeframe, limit=limit)
    df = normalize(bars_to_df(bars))
    df = calculate_indicators(df)
    eng = get_yolo_engine()
    res = eng.predict(df)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "yolo": {
            "pattern": res.pattern,
            "confidence": res.confidence,
            "raw": res.raw,
            "all_detections": res.all_detections,
            "available": eng.is_ready(),
            "model": eng.get_model_info(),
        },
        "chart_url": f"/chart?symbol={symbol}&timeframe={timeframe}&limit={limit}",
        "annotated_url": f"/yolo/chart?symbol={symbol}&timeframe={timeframe}&limit={limit}",
    }


@router.get("/yolo/chart")
async def yolo_chart(
    symbol: str = Query(..., examples=["BTCUSD"]),
    timeframe: str = Query(..., examples=["1h"]),
    limit: int = Query(120, ge=20, le=500),
):
    """YOLO annotated chart – kutularla birlikte (görsel teyidi gör)."""
    from app.providers import get_provider_for_symbol
    from app.data.normalize import bars_to_df, normalize
    from app.indicators import calculate_indicators
    from app.vision.yolo import get_yolo_engine

    try:
        provider = get_provider_for_symbol(symbol)
        bars = await provider.get_bars(symbol, timeframe, limit=limit)
        df = normalize(bars_to_df(bars))
        df = calculate_indicators(df)
        eng = get_yolo_engine()
        annotated, yr = eng.predict_annotated(df)
        if annotated is None:
            raise HTTPException(status_code=503, detail=yr.raw.get("error", "yolo not ready"))
        return Response(content=annotated, media_type="image/png", headers={"Cache-Control": "no-cache", "X-YOLO-Pattern": yr.pattern or "", "X-YOLO-Confidence": str(yr.confidence or "")})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"yolo chart failed: {e}")
