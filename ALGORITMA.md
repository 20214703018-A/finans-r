# Finansör — AI Market Pattern Scanner · Algoritma ve Sistem Dokümanı

**Versiyon:** MVP 0.3 · **Tarih:** 2026-08-31  
**Kod kökü:** `/Users/acar/Documents/finansör`  
**Prensip:** Önce sayısal motor, YOLO ikinci görüş, LLM açıklama katmanı. Asla LLM/YOLO fiyatı yorumlamaz.

---

## 1. Genel Akış (§47 Sıralı, Deterministik)

```
1 Market Data (Kraken /public/OHLC)          → app/providers/kraken.py:1
2 Normalize (Polars, timestamp UTC, sort)    → app/data/normalize.py:1
3 Quality (dup/missing/NaN/spike/zero_vol)   → app/data/quality.py:1
4 Indicators (EMA/ADX/RSI/ATR/RVOL/OBV/VWAP/MACD) → app/indicators/__init__.py:8
5 Swing (SciPy find_peaks + ATR-adaptive)    → app/patterns/swings.py:30
6 Pattern (DT/DB/H&S/IHS/Triangle/Wedge)     → app/patterns/*
7 Breakout                                   → app/analysis/breakout.py:1
8 Volume (RVOL/OBV/vol_trend)                → app/indicators/volume.py:1
9 Trend/Regime                               → app/indicators/trend.py:1 + app/analysis/regime.py:1
10 S/R Zone                                  → app/analysis/support_resistance.py:1
11 YOLO (HF foduucom/stockmarket-pattern-detection-yolov8) → app/vision/yolo.py:1
12 Scoring (100)                             → app/analysis/scoring.py:1
13 Trading Plan (giriş/stop/hedef/RR/süre)    → app/analysis/plan.py:1
14 Age (yaş/bayatlık/sonrası hareket)         → app/analysis/age.py:1
15 Signal (pattern yoksa MACD+RSI fırsatı)    → app/analysis/signal.py:1
16 Reasoning (LLM/fallback, skoru değiştirmez) → app/reasoning/client.py:1
```
Her adım aynı input → aynı output (random yok, seed sabit). Skor hesabı tüm OHLCV + tüm indikatörleri okur (`_last` ile kanıt `scores._debug` içinde).

---

## 2. Market Data Layer

**Provider interface** `app/providers/base.py:14` `MarketDataProvider.get_bars(symbol, timeframe, limit) → list[Bar]`.  
**Bar** `app/providers/base.py:8` `asset_id/symbol/exchange/timeframe/timestamp/open/high/low/close/volume` (timestamp UTC, open time).

**Kraken** `app/providers/kraken.py:1` `GET /0/public/OHLC?pair=XBTUSD&interval=60`  
Pair map: `BTCUSD→XBTUSD`, `DOGEUSD→XDGUSD` vb. Hata: `error[]` → exception. `limit` son N bar.

**Alpaca** `app/providers/alpaca.py:1` (Nasdaq, `feed=iex` free, prod `SIP` önerilir), **BIST** `app/providers/bist.py:1` stub (Matriks/İdeal).

**Routing** `app/providers/__init__.py:1` `SYMBOL_PROVIDER_MAP` (`BTCUSD→kraken`, `AAPL→alpaca`, `THYAO→bist`).

**Normalize** `app/data/normalize.py:1` `bars_to_df` → Polars, `timestamp` UTC, sort + dedup.  
**Quality** `app/data/quality.py:1` `validate_data(df, tf)`:
- `dup = n - n_unique(timestamp)`
- `nan_count` (open/high/low/close/volume)
- `zero_volume_count` (>10% ise `issue`)
- `out_of_order`
- `extreme spike` `|Δclose|/close >20%` → warning
- `missing ~` `delta >1.5*expected` (`15m→900s, 1h→3600s` vb)

---

## 3. İndikatörler (Hepsi `Polars` + `numpy`, TA-Lib yok, saf Python)

### 3.1 Trend `app/indicators/trend.py:1`
- **EMA** `ema(s, p)` `α=2/(p+1)` Wilder değil klasik EMA. `EMA20, EMA50, EMA200`.
- **ADX14** `compute_adx(high,low,close)` Wilder smoothing `atr_w, plus_w, minus_w → plus_di, minus_di → dx → adx`. `adx>25` trending.
- **Slope** `(EMA20[t]-EMA20[t-5])/EMA20[t-5]*100` (%/5 bar).

`classify_trend(row)`:
```
close>ema20>ema50>ema200 & adx>25 → STRONG_UPTREND
close>ema20>ema50 → UPTREND
close<ema20<ema50<ema200 & adx>25 → STRONG_DOWNTREND
close<ema20<ema50 → DOWNTREND else RANGE
```
`add_trend_indicators(df)` sütun ekler.

### 3.2 Momentum `app/indicators/momentum.py:1`
- **RSI14** Wilder `avg_gain/loss → rs → 100-100/(1+rs)`. NaN ilk 14.
- **Divergence** `detect_rsi_divergence` son 40 bar: `find_peaks(close, distance=5)` lows: `close[i2]<close[i1] & rsi[i2]>rsi[i1]` → bullish, highs tersi bearish.

### 3.3 Volatility `app/indicators/volatility.py:1`
- **ATR14** Wilder `tr = max(h-l, |h-close_prev|, |l-close_prev|) → atr[13]=mean(tr[:14]), atr[i]=(prev*(13)+tr[i])/14`
- **ATR%** rolling 100 pencerede `percentile = (window<cur).mean()*100` (regime).

### 3.4 Volume `app/indicators/volume.py:1`
- **RVOL** `vol / SMA20(vol)` `window 20`. Label: `<0.8 weak, 0.8-1.2 normal, 1.2-1.5 strong, >1.5 very_strong`.
- **OBV** `obv[i]=obv[i-1]±vol` close yönüne göre.
- **vol_sma20** ve **vol_trend** `(sma[t]-sma[t-5])/sma[t-5]`.
- **VWAP** rolling 20 `pv/vol` (`typical=(h+l+c)/3`).

### 3.5 MACD `app/indicators/macd.py:1` (yeni)
- `EMA12 - EMA26 → macd`, `EMA9(macd) → signal`, `hist=macd-signal`. `macd_state(last)` `m>s & h>0 → bullish`, `m<s & h<0 → bearish`.

`calculate_indicators(df)` sırayla 6’sını ekler, son bar `df.row(-1)` tümüyle skorlamada kanıt.

---

## 4. Swing Engine `app/patterns/swings.py:30` (§12-13)

1. `find_peaks(high, distance=3)` highs, `find_peaks(-low, distance=3)` lows.
2. ATR-adaptive filtre **yalnız** `price_diff < ATR*1.5 && bar_dist <10` ise zayıfı ele (daha ekstremi tut). Eskiden sadece fiyat bakıp M_Head/W_Bottom benzer tepeleri yutuyordu, düzeltildi → `double_top` benzer tepeler korunur.
3. Alternatif `zigzag_swings` §13 state machine pivot±ATR*1.5 reversal.

Çıktı `SwingResult(highs, lows, all_sorted)` indeks+price.

---

## 5. Pattern Detection

### 5.1 Double Top/Bottom `app/patterns/double_top.py:1` §20-21
`detect_double_top`:
- İki `highs[i], highs[i+1]` arası `valley = min(lows between)`.
- `atr_ref = atr[peak2] or mean(atr) or close*0.02`
- `peak_diff = |p1-p2| ≤ ATR*0.75` else at
- `valley_depth = min(p1,p2)-valley ≥ ATR*1.0` else at
- `bar_dist = p2-p1 ∈ [5,80]`
- `neckline = valley`, `height = (p1+p2)/2 - neck`, `target = neck - height`, `invalidation = max(p1,p2)+ATR*0.5`
- `geometry = 0.45*(1-diff/(0.75ATR)) +0.35*min(1,depth/(1.5ATR)) +0.20*(1-|dist-22|/30)` clip 0-1
- Status: `close < neck-ATR*0.10` breakout, 3 bar re-entry → `failed` else `confirmed`, yakında ise `breakout_pending`, `geom<0.45 → forming`. Top 5.

`detect_double_bottom` simetrik (`neckline=peak`, `target=neck+height`).

### 5.2 Head & Shoulders `app/patterns/head_shoulders.py:1` §22-23
Üç `highs` (`l,h,r`) + iki `lows` `neck1, neck2` arası. `h>l & h>r`, `|l-r| ≤ ATR*1.2 or 2% price`, `head_prom = h-max(l,r) ≥ ATR*0.8`. `neckline=(n1+n2)/2`, `target=neck±height`. `geometry =0.4*shoulder_sim+0.4*prom/2ATR+0.2*(1-slope/2)`. Status breakout `close <> neck±ATR*0.12`.

### 5.3 Triangle `app/patterns/triangles.py:1` §24
Son 80 bar `highs/lows` `polyfit` → `h_slope,h_inter,resid` `l_slope,l_inter`. Normalize `slope/price`. `horiz =0.0002`. `sym: h< -horiz & l> horiz`, `asc: |h|<horiz & l>horiz`, `desc: h<-horiz & |l|<horiz`. Converge `h_slope < l_slope`, `apex = (l_inter-h_inter)/(h_slope-l_slope)`, `apex_ahead = apex - n ∈ [-10,60]` ideal 15. `geometry=0.45*resid_score+0.25*sym+0.30*apex`. Son bar kanala göre `confirmed/breakout_pending`.

### 5.4 Wedge `app/patterns/wedges.py:1` §25
Aynı fit, `same_sign` (`h>0&l>0 → rising`, `h<0&l<0 → falling`). `rising: l>h` (alt daha dik), `falling: h>l`. `apex_ahead` 0-80 ideal 20, `geometry=0.55*resid+0.45*apex`.

---

## 6. Breakout `app/analysis/breakout.py:1` §26-27

- `atr_last = atr[-1] or mean(atr) or close*0.02`
- `body = |close-open|`, `body_atr = body/atr`
- Neckline tipler: `head_shoulders/double_top → down (neck-close)/atr`, `inverse/double_bottom → up (close-neck)/atr`, triangle/wedge → `upper/lower` `h_slope*i+h_inter`.
- `quality`: `strength<0.25 weak, <0.5 moderate, ≥0.5 strong`, `body_atr<0.3 → weak`, `fake` ilk breakout + 3 bar re-entry → `failed`.
- Proximity breakout yoksa `min(dist_up, dist_down)`.

---

## 7. Support/Resistance `app/analysis/support_resistance.py:1` §19

Swing `highs+lows` sort → `|p-mean(cluster)| < ATR*0.6` aynı zone. `zones = {center,count,low,high}` count desc sort top 5. `nearest_atr = |level-center|/ATR`, `confluence=count`. `score =0.6*(1-nearest/1.2)+0.4*min(1,count/4)`.

---

## 8. Regime `app/analysis/regime.py:1` §29

`adx, atr_pct, slope, close/ema200`.
- `adx>25 & slope>0.15 → TRENDING_UP`, `<-0.15 → TRENDING_DOWN`
- `atr_pct>75 HIGH_VOL, <25 LOW_VOL`
- else `RANGE`. `volatility` etiketi ayrı.

---

## 9. Multi-Timeframe `app/analysis/multi_timeframe.py:1` §28
`evaluate_mtf_context(primary, {4h,1d})` `classify_trend` per TF, `raw = Σ (1d 10, 4h 15)` bullish + / bearish -. `mtf_adjusted_score(type, raw)` triangle nötr `abs(raw)//3`, bullish/bearish yönlü ceza/bonus.

---

## 10. YOLO `app/vision/yolo.py:1` + `app/vision/chart.py:1` §30-32

- **Chart** `render_chart(df, 1280x720, 120)` `mplfinance` yahoo style, no volume/mav, `Date` index, `tight_layout`, tick gizli, `dpi 100` → PNG bytes. `save_chart_png`.
- **Model** HF `foduucom/stockmarket-pattern-detection-yolov8` YOLOv8s 87.7MB `models/stockmarket_yolov8.pt` `app/config.py:20` `YOLO_HF_REPO/FILENAME` auto-download `huggingface_hub hf_hub_download` + copy. `conf_min 0.40`.
- **Labels** `['Head and shoulders bottom'→inverse_head_shoulders, 'Head and shoulders top'→head_shoulders, 'M_Head'→double_top, 'W_Bottom'→double_bottom, 'Triangle'→triangle, 'StockLine'→None(ignored)]` `YOLO_CANONICAL`.
- **Engine** `YoloEngine` lazy singleton `get_yolo_engine()`. `predict(df)`: render → temp PNG → `model.predict(conf=0.40)` → `boxes.conf/cls/xyxy` → `detections [{label,canonical,conf,cls_id,bbox}]` (StockLine filtre) → best `canonical` `confidence`. `predict_annotated(df)`: `r.plot()` (BGR→RGB) annotated PNG + aynı detections.
- **Confirmation** `confirm(df, type)` mekansal + tip: `type_match` + `visible_start = n-120`, `pat_center = mean(indices)`, `yolo_center = (bbox_x_center-left)/plot_w*120 + visible_start`, `pat_visible = pat_center ≥ visible_start`, `|yolo_center - pat_center| ≤20` → `is_confirmation:true` else `false` (çok öncede veya uzak → `None` nötr). StockLine yalnız → `None`.

**Skor etkisi** `app/analysis/scoring.py:131` 5/100: `match & conf≥0.40 → (conf-0.40)/0.60*5`, mismatch (wedge hariç) → `-2` clamp 0, wedge/StockLine nötr.

**Endpointler** `/chart` temiz PNG, `/yolo/chart` kutulu PNG, `/yolo/preview` JSON `{yolo, chart_url, annotated_url}`.

---

## 11. Scoring v2 `app/analysis/scoring.py:1` (§33-34, deterministik)

`calculate_score(pattern, df, breakout, volume_info, trend_info, regime_info, sr_info, yolo_info, mtf_info)` tüm son barı `_last` ile okur (`open/high/low/close/volume, ema20/50/200, adx, slope, rsi, atr, atr_pct, rvol, obv, vol_sma, vol_trend, vwap`), aynı input → aynı 100.

- **geom 30** `pattern.geometry_score*30`
- **breakout 20** `strong 20 moderate 14 weak 7 none 3-8` + `body_atr<0.25 -3` + `ATR% >75 & weak -2` + `VWAP yönü ±1`
- **volume 15** `RVOL 3/8/12/15` + `OBV slope vs price ±2` + `vol_trend ±1` + `rvol<0.9 & breakout -6` + `zero_vol -5`
- **trend 15** `EMA hizası 0-5 + ADX 0-5 + slope 0-3 + EMA200 mesafe 0-2` (+ `HIGH_VOL -1`, type mismatch -1) veya `mtf` `(-10…15)→0…15`
- **mom 10** `RSI 30-55 bullish 45-70 bearish + divergence 10`
- **yolo 5** üstte
- **S/R 5** `sr_score*5` + `VWAP <0.4 ATR & breakout → +1`
- `_debug` tüm indikatör son değerleri kanıt.

`final<60 discard 60 weak 70 watch 80 strong 90 exceptional`. `watch+` default scan `min_score 70` `app/api/schemas.py:1` (zorlama yok, `include_weak` ile 60).

---

## 12. Trading Plan `app/analysis/plan.py:1` (§20-21, §26-27, timeframe-aware)

`build_trading_plan(pattern, df, breakout, scores, timeframe)`:

```
is_bull = type in {double_bottom,...}
height = |target-neck|
entry = neck ± ATR*0.12 (buffer)
stop  = invalidation (max peak+0.5ATR or min trough-0.5ATR)
target = neck ± height
risk = |entry-stop|, reward = |target-entry|, rr = reward/risk
k = 0.55 (trend≥12 →0.70, ≤5 →0.45)
est_bars = height/(ATR*k) clamp 4-60, ATR% >70 *0.8, <30 *1.25
est_hours = est_bars * tf_hours (15m 0.25,1h1,4h4,1d24) → "5 mum (~5sa /0.2g)" etc
valid_bars = max(12, est_bars*1.5) → "Breakout +12 mum (12sa) veya stop"
chart_window = min(n,120) * tf_hours
criteria 7: geom≥0.65, breakout moderate/strong, rvol≥1.2, trend≥9, mom≥7/div, S/R≥3, yolo≥2
valid = status∈{mature,breakout_pending,confirmed} & (breakout_ok or pending) & geom_ok
is_actionable = valid & final≥70 & green≥4 & not fake
valid_where = "Fiyat {entry} üzerinde/altında kapanış + hacim + YOLO"
invalid_where = "Fiyat {stop} altına/üstüne kapanış"
```

---

## 13. Age `app/analysis/age.py:1` (48 mum örneği)

`evaluate_age(df, pattern, tf)`:
```
max_idx = max(indices), age_bars = n-1-max_idx, age_hours = age_bars*tf_min/60
freshness: ≤15 1.0 taze, ≤35 0.6 orta, ≤60 0.3 bayat, >60 0.1 çok bayat → skor -4/-8 `app/pipeline.py:140`
post: closes[max_idx+1:] chg, max_fav/adv, hit_target/stop (bool np.any), post_label:
  hedef&!stop → kâr realizasyonu, stop&!hedef → geçersiz, ikisi → volatil, yatay → neckline takibi
```

---

## 14. Indicator Signal `app/analysis/signal.py:1` (formasyon yoksa fırsat)

`indicator_signal(df)` MACD+RSI+ADX+RVOL+VWAP deterministik:
- trend `close>ema20>ema50 & adx>25 & slope>0.05` → +25 `long` (bearish simetrik)
- RSI `30-38 & bullish_div → +20`, `<32 →+12`, `>68 →+12` vb
- MACD `bullish & hist>0 & hist_trend bullish_güçleniyor (h[-1]>h[-2]>h[-3])` → +25
- RVOL `≥1.5 +10, ≥1.0 +4`, VWAP `|dist|<0.3 +5, >1.5 -5`
- `score≥60 & direction & ≥2 bileşen (Trend/MACD/RSI)` → fırsat `pattern_type: indicator_signal` (aksi None). `pipeline` `enriched` boş veya hepsi <60 ise ekler.

---

## 15. Pipeline `app/pipeline.py:41`

`async analyze_asset(symbol, timeframe, limit=300)` 13 adım yukarıda, YOLO cache (tek predict), scoring, plan, age, reasoning, `_sanitize` NaN/Inf→None + np.bool→bool, sort final desc, `indicator_signal` fallback. `health` greenlet hatası yakalanır, DB olmadan da çalışır.

**Örnek BTCUSD 1h 120** canlı: `close 77800 adx 421 slope -0.43 atr 452 rvol 0.74 vwap 78205 → double_top peak1:2 valley:11 peak2:19 geom 0.95 → 28.8, breakout none 11.1, volume 5, trend 12, mom 5, yolo 0, S/R 2 → final 66.9 weak, age 10 bar taze, est 5 mum (~5sa), YOLO M_Head 71.6% mekansal check → is_confirmation true/false.

---

## 16. API `app/api/analyze.py:1` + `assets.py:1` + `main.py:1`

- `GET /health` `GET /` (frontend `index.html` varsa serve, yoksa JSON) `GET /app`
- `GET /assets`, `/assets/timeframes`, `/assets/patterns`, `/assets/yolo/status` `POST /assets/yolo/reload`
- `POST /analyze {symbol, timeframe 15m/1h/4h/1d, limit 50-1000}` → full `pipeline` sonucu
- `POST /scan {symbols[≤20], timeframe, limit, min_score 70 default, include_weak}` concurrent semaphore 4
- `POST /backtest?lookback=1000` walk-forward `patterns_found/evaluated/aggregate {win_rate, avg_return_5/10/20, expectancy, mfe/mae}`
- `GET /chart?symbol&timeframe&limit` PNG 1280×720
- `GET /yolo/preview` JSON + `chart_url/annotated_url` + `bbox`
- `GET /yolo/chart` annotated PNG `X-YOLO-Pattern` header

CORS `*`, Static `/static` → `frontend/`.

---

## 17. Frontend `frontend/index.html:1`

Tailwind + FontAwesome, `max-w 1400`, pills, `limit/min_score/include_weak`, `Chart (YOLO'nun gördüğü)` `Temiz Chart / YOLO Kutulu` toggle, `Göstergeler` (close/EMA/RSI/ATR/RVOL/VWAP), `Data Quality`, `Patternler (n)` `60/70/80` badge, kart başına `geom/breakout/volume/trend/mom/yolo/S/R` bar, `Giriş/Stop/Hedef/RR/Durum`, `Alım Kriterleri 7` ✓/○, `Yaş` (`109 mum ~109sa çok bayat`), `Breakout/rvol/rsi`, `Reasoning` + `Raw` (`prices/breakout/yolo/bbox`), `YOLO Görsel Teyit Detayı` + `Gösterge Sinyali` mor kutu.

**JS** `loadAssets / loadYoloStatus / doAnalyze / doYolo / doScan`, `showChartTab / showYoloTab`, auto `doAnalyze` onload.

---

## 18. DB `app/db/models.py:1` + `session.py:1` + `seed.py:1`

`assets(id PK symbol.exchange, exchange/mic/timezone/currency/asset_type/is_active)`, `candles(asset_id,timeframe,timestamp, OHLCV) unique(asset_tf_ts)`, `patterns(asset_id,timeframe,pattern_type, scores 7, final_score, status, details JSON, yolo, neckline/invalidation/target)`, `analyses`, `users`, `watchlists`. `asyncpg` `postgresql+asyncpg://...` + `sync` alembic `alembic.ini`. `seed_assets` 17 asset (10 crypto Kraken + 4 Nasdaq Alpaca + 3 BIST). `init_db` `create_all` lifespan'da.

---

## 19. Config `app/config.py:1`

`Pydantic BaseSettings` `.env` → `DATABASE_URL`, `KRAKEN_BASE_URL`, `ALPACA_*`, `YOLO_MODEL_PATH=models/stockmarket_yolov8.pt`, `YOLO_CONF_MIN 0.40`, `YOLO_HF_REPO/FILENAME`, `YOLO_AUTO_DOWNLOAD true`, `OPENAI_API_KEY/MODEL`, `TIMEFRAMES`, `crypto_symbols`.

---

## 20. Backtest `app/analysis/backtest.py:1` (§41-44)

`evaluate_pattern_outcome(df, pattern)` entry `max_idx+1` `close>neck (bull) or <neck (bear)`, 20 bar `high/low` target/stop hit, `r5/r10/r20`, `mfe/mae`. `aggregate_backtest` `win_rate, expectancy = win*mfe - (1-win)*|mae|`, `false_positive`. `walk_forward_splits` 60/20 +80/20.

---

## 21. Scheduler `app/scheduler.py:1` (§38)

`APScheduler AsyncIOScheduler` `IntervalTrigger 15m/1h/4h/1d` `last_scan_results` memory (no Redis/Celery).

---

## 22. Ops

`requirements.txt` `fastapi, uvicorn, pydantic, httpx, polars, numpy, scipy, mplfinance, matplotlib, sqlalchemy, asyncpg, alembic, apscheduler, openai, torch, ultralytics, huggingface_hub, scikit-learn`.  
`Dockerfile` `python:3.12-slim` TA-Lib C build + pip + uvicorn. `docker-compose.yml` `db:16-alpine` + `api:8000`. `scripts/download_yolo.py` `scripts/analyze_one.py` `scripts/yolo_only.py` (PNG+JSON+bbox). `pytest tests/test_pipeline_offline.py` 7 test (normalize/indicators/swings/double_top/breakout).

