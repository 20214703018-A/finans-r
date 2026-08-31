#!/usr/bin/env python3
"""Tek hisse canlı analiz + YOLO – kullanım: python scripts/analyze_one.py BTCUSD 1h"""
import asyncio, sys, json
from app.pipeline import analyze_asset
from app.vision.yolo import get_yolo_engine

async def main():
    symbol = sys.argv[1] if len(sys.argv)>1 else "BTCUSD"
    tf = sys.argv[2] if len(sys.argv)>2 else "1h"
    limit = int(sys.argv[3]) if len(sys.argv)>3 else 300
    print(f"→ {symbol} {tf} limit={limit} (Kraken canlı)")
    j = await analyze_asset(symbol, tf, limit=limit, include_reasoning=True)
    print(f"\nasset: {j['asset_id']}  quality ok={j['quality']['ok']}  patterns={j['pattern_count']}")
    ind = j['indicators']
    print(f"close {ind['close']:.1f}  trend {ind['trend']}  regime {ind['regime']['regime']}  rsi {ind['rsi']:.1f}  atr {ind['atr']:.0f}  rvol {ind['rvol']:.2f}")
    print(f"yolo model: {get_yolo_engine().get_model_info()['resolved_path']}  labels={get_yolo_engine().get_model_info()['labels']}")
    if not j['patterns']:
        print("Pattern yok (discard <60) – limit artır veya timeframe değiştir")
        return
    for i,p in enumerate(j['patterns'][:5],1):
        y=p['yolo']
        print(f"\n[{i}] {p['pattern_type']}  {p['status']}  SCORE {p['final_score']} ({p['scores']['label']})")
        print(f"    geom {p['scores']['geometry']}/30 br {p['scores']['breakout']}/20 vol {p['scores']['volume']}/15 trend {p['scores']['trend']}/15 mom {p['scores']['momentum']}/10 yolo {p['scores']['yolo']}/5 sr {p['scores']['support_resistance']}/5")
        print(f"    neckline {p['neckline']:.1f}  target {p['target']:.1f}  inv {p['invalidation']:.1f}")
        print(f"    breakout {p['breakout']['quality']} fake={p['breakout']['fake_breakout']} atr_dist={p['breakout']['breakout_strength_atr']:.2f}")
        print(f"    YOLO → pattern={y.get('pattern')} conf={y.get('confidence')} is_conf={y.get('is_confirmation')} available={y.get('available')} raw={y.get('raw',{}).get('label') if y.get('raw') else '-'}")
        print(f"    reasoning: {p['reasoning'][:180].replace(chr(10),' ')}...")
        if i==1:
            print(f"    indices {p['indices']} prices { {k:round(v,1) for k,v in p['prices'].items()}}")

if __name__=="__main__":
    asyncio.run(main())
