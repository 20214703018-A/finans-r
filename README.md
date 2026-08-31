# Finansör – AI Market Pattern Scanner (MVP)

Tek Python backend – FastAPI + Polars + SciPy + mplfinance + YOLO.

## Hızlı Başlangıç

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt  # TA-Lib C lib için: brew install ta-lib (macOS) veya Dockerfile
cp .env.example .env
# DB olmadan da çalışır; DB için:
docker compose up -d db
alembic upgrade head  # veya app otomatik init_db yapar
uvicorn app.main:app --reload
# http://localhost:8000/docs
```

## Endpointler
- `GET /health`, `GET /`, `GET /assets`, `GET /assets/timeframes`, `GET /assets/patterns`
- `POST /analyze`  `{"symbol":"BTCUSD","timeframe":"4h"}`
- `POST /scan`     `{"symbols":["BTCUSD","ETHUSD"],"timeframe":"4h"}`
- `POST /backtest` `{"symbol":"BTCUSD","timeframe":"1d"}` + `?lookback=1000`

## Mimari
```
Kraken API -> normalize -> quality -> indicators (EMA/ADX/RSI/ATR/RVOL/VWAP)
         -> ATR-Adaptive Swing -> Pattern Engines (DT/DB/H&S/Triangle/Wedge)
         -> breakout / volume / trend / regime / S/R -> YOLO confirm -> scoring -> reasoning
         -> FastAPI -> PostgreSQL
```

## YOLO
Hazır model: [`foduucom/stockmarket-pattern-detection-yolov8`](https://huggingface.co/foduucom/stockmarket-pattern-detection-yolov8) (YOLOv8s, 6 sınıf: `Head and shoulders top/bottom`, `M_Head`→double_top, `W_Bottom`→double_bottom, `Triangle`, `StockLine`).
- İlk çalıştırmada `models/stockmarket_yolov8.pt` HF'den oto-indirilir (`YOLO_AUTO_DOWNLOAD=true`). Offline ise `available:false` fallback.
- Manuel indir: `python scripts/download_yolo.py` veya `python scripts/download_yolo.py --force`
- Boyut: ~88 MB. `app/vision/yolo.py:13` `YOLO_CANONICAL` mapping StockLine'i yok sayar (ceza yok), Triangle family match yapar.
- Durum: `GET /assets/yolo/status`, yenile: `POST /assets/yolo/reload`
- `YOLO_CONF_MIN=0.40` (§32, scoring 5/100).

## BIST/Nasdaq
- Nasdaq: `AlpacaProvider` (free IEX; prod'da SIP önerilir)
- BIST: `BistProvider` stub – lisanslı vendor (Matriks/İdeal) veya TwelveData ile doldurulacak.

## Test
```bash
pytest -q
```
