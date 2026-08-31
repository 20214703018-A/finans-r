"""OHLCV normalization – all providers -> canonical Polars DataFrame."""
import polars as pl
from datetime import timezone
from app.providers.base import Bar


def bars_to_df(bars: list[Bar]) -> pl.DataFrame:
    if not bars:
        return pl.DataFrame(
            schema={
                "asset_id": pl.String,
                "symbol": pl.String,
                "exchange": pl.String,
                "timeframe": pl.String,
                "timestamp": pl.Datetime("ms", "UTC"),
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "volume": pl.Float64,
            }
        )
    df = pl.DataFrame(
        {
            "asset_id": [b.asset_id for b in bars],
            "symbol": [b.symbol for b in bars],
            "exchange": [b.exchange for b in bars],
            "timeframe": [b.timeframe for b in bars],
            "timestamp": [b.timestamp.astimezone(timezone.utc) for b in bars],
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
            "volume": [b.volume for b in bars],
        }
    )
    # Ensure UTC and sorted
    df = df.with_columns(pl.col("timestamp").dt.replace_time_zone("UTC")).sort("timestamp")
    return df


def normalize(df: pl.DataFrame) -> pl.DataFrame:
    """Idempotent normalize: sort, dedup, cast."""
    if df.is_empty():
        return df
    df = df.sort("timestamp").unique(subset=["timestamp"], keep="last").sort("timestamp")
    # Cast numeric
    for c in ["open", "high", "low", "close", "volume"]:
        df = df.with_columns(pl.col(c).cast(pl.Float64))
    return df
