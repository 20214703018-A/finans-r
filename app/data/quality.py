"""Data Quality Layer – §11."""
import polars as pl
import numpy as np
from dataclasses import dataclass


@dataclass
class QualityReport:
    ok: bool
    issues: list[str]
    warnings: list[str]
    duplicate_count: int
    missing_count: int
    nan_count: int
    zero_volume_count: int


def validate_data(df: pl.DataFrame, timeframe: str = "1h") -> QualityReport:
    issues: list[str] = []
    warnings: list[str] = []

    if df.is_empty():
        return QualityReport(False, ["empty dataframe"], [], 0, 0, 0, 0)

    # Duplicate candles (timestamp)
    dup = df.height - df.unique(subset=["timestamp"]).height

    # NaN check
    nan_count = 0
    for c in ["open", "high", "low", "close", "volume"]:
        if c in df.columns:
            nan_count += df.filter(pl.col(c).is_null() | pl.col(c).is_nan()).height

    # Zero volume
    zero_vol = df.filter(pl.col("volume") == 0).height if "volume" in df.columns else 0

    # Out-of-order timestamp
    ts = df["timestamp"].to_list()
    if ts != sorted(ts):
        issues.append("out_of_order_timestamp")

    # Extreme spike: close change > 20% in one bar (crypto) – warning not fatal
    if df.height >= 2:
        closes = df["close"].to_numpy()
        pct = np.abs(np.diff(closes) / closes[:-1])
        if np.any(pct > 0.20):
            warnings.append(f"extreme_price_spike max={pct.max():.2%}")

    # Missing candles – estimate expected count vs actual (warn if >5% missing)
    # Only for intraday where gaps are not expected (crypto is 24/7, so simple check)
    if df.height >= 2:
        # infer expected delta from timeframe
        tf_min = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}.get(timeframe, 60)
        expected_delta = tf_min * 60  # seconds
        # count gaps > 1.5x expected
        missing = 0
        for i in range(1, len(ts)):
            delta = (ts[i] - ts[i - 1]).total_seconds()
            if delta > expected_delta * 1.5:
                # estimate missing bars in gap
                missing += int(round(delta / expected_delta)) - 1
        if missing > 0:
            warnings.append(f"missing_candles~{missing}")

    ok = len(issues) == 0 and dup == 0 and nan_count == 0

    # zero volume alone is warning unless >10% of bars
    if zero_vol > 0 and zero_vol / df.height > 0.10:
        issues.append(f"excessive_zero_volume {zero_vol}/{df.height}")

    return QualityReport(
        ok=ok,
        issues=issues,
        warnings=warnings,
        duplicate_count=dup,
        missing_count=missing if 'missing' in locals() else 0,
        nan_count=nan_count,
        zero_volume_count=zero_vol,
    )


def assert_quality(df: pl.DataFrame, timeframe: str = "1h") -> None:
    report = validate_data(df, timeframe)
    if not report.ok:
        raise ValueError(f"Data quality failed: issues={report.issues} warnings={report.warnings} dup={report.duplicate_count} nan={report.nan_count}")
