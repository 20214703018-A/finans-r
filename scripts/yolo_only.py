#!/usr/bin/env python3
"""YOLO yalnız – chart render + HF model predict. Kullanım: python scripts/yolo_only.py BTCUSD 1h"""
import sys, asyncio
import polars as pl
from app.providers.kraken import KrakenProvider
from app.data.normalize import bars_to_df, normalize
from app.indicators import calculate_indicators
from app.vision.yolo import get_yolo_engine, reset_yolo_engine
from app.vision.chart import render_chart
from pathlib import Path

async def main():
    symbol = sys.argv[1] if len(sys.argv)>1 else "BTCUSD"
    tf = sys.argv[2] if len(sys.argv)>2 else "1h"
    limit = int(sys.argv[3]) if len(sys.argv)>3 else 120
    out = sys.argv[4] if len(sys.argv)>4 else f"/tmp/{symbol}_{tf}_chart.png"
    print(f"→ {symbol} {tf} → {out}")
    p = KrakenProvider()
    bars = await p.get_bars(symbol, tf, limit=limit)
    print(f"  {len(bars)} bar  {bars[0].timestamp} → {bars[-1].timestamp}")
    df = normalize(bars_to_df(bars))
    df = calculate_indicators(df)
    # chart
    png = render_chart(df, candles=120)
    Path(out).write_bytes(png)
    print(f"  chart 1280x720 120 mum kaydedildi: {out} ({len(png)} byte)")
    # yolo
    reset_yolo_engine()
    eng = get_yolo_engine()
    info = eng.get_model_info()
    print(f"  YOLO ready={info['available']}  {info['resolved_path']}  labels={info['labels']}")
    res = eng.predict(df)
    print(f"  predict → pattern={res.pattern}  conf={res.confidence}  raw={res.raw}")
    if res.all_detections:
        for d in res.all_detections:
            bbox = d.get('bbox')
            print(f"    - {d['label']} → {d['canonical']}  conf={d['confidence']:.2f}  bbox={bbox}")
        # annotated
        annotated, _ = eng.predict_annotated(df)
        if annotated:
            ann_path = out.replace(".png", "_yolo.png")
            Path(ann_path).write_bytes(annotated)
            print(f"  annotated (kutulu) kaydedildi: {ann_path} ({len(annotated)} byte)  → /yolo/chart ile aynı")
    else:
        print("    (tespit yok – confidence <0.40 veya StockLine yalnız)")
    # detections JSON
    jpath = out.replace(".png", "_yolo.json")
    import json
    Path(jpath).write_text(json.dumps({"symbol":symbol,"timeframe":tf,"detections":res.all_detections or [], "best": {"pattern":res.pattern,"confidence":res.confidence}}, indent=2))
    print(f"  JSON: {jpath}")

if __name__=="__main__":
    asyncio.run(main())
