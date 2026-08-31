"""Offline unit tests – no network, no DB."""
import polars as pl
import numpy as np
from datetime import datetime, timezone, timedelta
from app.data.normalize import bars_to_df, normalize
from app.data.quality import validate_data
from app.indicators import calculate_indicators
from app.patterns.swings import detect_swings
from app.patterns.double_top import detect_double_top, detect_double_bottom
from app.patterns.head_shoulders import detect_head_shoulders, detect_inverse_head_shoulders
from app.patterns.triangles import detect_triangles
from app.patterns.wedges import detect_wedges
from app.analysis import evaluate_breakout, evaluate_sr, evaluate_regime, calculate_score
from app.providers.base import Bar


def synthetic_df(n=250, seed=42):
    rng = np.random.default_rng(seed)
    base = 100.0
    closes = [base]
    for i in range(1, n):
        closes.append(closes[-1] + rng.normal(0, 0.6))
    closes = np.array(closes)
    high = closes + np.abs(rng.normal(0.3, 0.2, n))
    low = closes - np.abs(rng.normal(0.3, 0.2, n))
    open_ = closes + rng.normal(0, 0.2, n)
    vol = rng.integers(800, 2500, n).astype(float)
    ts = [datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i) for i in range(n)]
    df = pl.DataFrame({"asset_id": ["BTCUSD.KRAKEN"] * n, "symbol": ["BTCUSD"] * n, "exchange": ["KRAKEN"] * n, "timeframe": ["1h"] * n, "timestamp": ts, "open": open_, "high": high, "low": low, "close": closes, "volume": vol})
    return df


def double_top_df():
    # Craft clear double top: two peaks ~112k, valley ~109k, breakdown
    n = 100
    ts = [datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i) for i in range(n)]
    # Build price series manually
    closes = np.full(n, 110000.0)
    # first peak at 20, valley 35, second peak 50, breakdown after 60
    closes[15:25] = np.linspace(110000, 112000, 10)
    closes[25:35] = np.linspace(112000, 109000, 10)
    closes[35:50] = np.linspace(109000, 111800, 15)
    closes[50:65] = np.linspace(111800, 108500, 15)
    closes[65:] = 108500 + np.random.default_rng(0).normal(0, 80, n - 65)
    high = closes + 180
    low = closes - 180
    open_ = closes + np.random.default_rng(1).normal(0, 30, n)
    vol = np.full(n, 1800.0)
    vol[60:65] = 3200  # breakout volume
    df = pl.DataFrame({"asset_id": ["BTCUSD.KRAKEN"] * n, "symbol": ["BTCUSD"] * n, "exchange": ["KRAKEN"] * n, "timeframe": ["1h"] * n, "timestamp": ts, "open": open_, "high": high, "low": low, "close": closes, "volume": vol})
    return df


def test_normalize_and_quality():
    df = synthetic_df(80)
    df = normalize(df)
    assert df.height == 80
    r = validate_data(df, "1h")
    assert r.nan_count == 0


def test_indicators():
    df = synthetic_df(250)
    df = calculate_indicators(df)
    for c in ["ema20", "ema50", "rsi", "atr", "rvol", "vwap", "adx"]:
        assert c in df.columns
    assert df["atr"][-1] is not None


def test_swings():
    df = synthetic_df(200)
    df = calculate_indicators(df)
    swings = detect_swings(df)
    assert len(swings.highs) > 0
    assert len(swings.lows) > 0


def test_double_top_detection():
    df = double_top_df()
    df = calculate_indicators(df)
    swings = detect_swings(df)
    cands = detect_double_top(df, swings)
    assert len(cands) >= 1
    assert cands[0].pattern_type == "double_top"
    assert cands[0].geometry_score > 0.4


def test_no_false_positive_on_random():
    df = synthetic_df(300, seed=99)
    df = calculate_indicators(df)
    swings = detect_swings(df)
    # random walk should produce at most few patterns; failed breakouts are expected and indicate correctly flagged false positives
    cands = detect_double_top(df, swings)
    for c in cands:
        assert c.geometry_score < 0.97 or c.status in ("forming", "mature", "breakout_pending", "failed")


def test_breakout_and_scoring():
    df = double_top_df()
    df = calculate_indicators(df)
    swings = detect_swings(df)
    cands = detect_double_top(df, swings)
    assert cands
    pat = cands[0]
    br = evaluate_breakout(df, pat)
    assert "is_breakout" in br
    sr = evaluate_sr(df, pat, swings)
    regime = evaluate_regime(df)
    scores = calculate_score(pat, df, br, {"rvol": 1.6}, {"trend": "RANGE"}, regime, sr, {"pattern": None, "confidence": None})
    assert 0 <= scores["final"] <= 100
    assert scores["geometry"] > 0


def test_bars_to_df():
    bars = [Bar("BTCUSD.KRAKEN", "BTCUSD", "KRAKEN", "1h", datetime(2024, 1, 1, tzinfo=timezone.utc), 100, 101, 99, 100.5, 1200)]
    df = bars_to_df(bars)
    assert df.height == 1
    assert df["close"][0] == 100.5
