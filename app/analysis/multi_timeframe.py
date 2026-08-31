"""Multi-Timeframe Engine §28."""
import polars as pl
from app.indicators.trend import classify_trend


def evaluate_mtf_context(
    primary_df: pl.DataFrame,
    higher_dfs: dict[str, pl.DataFrame],  # e.g. {"4h": df_4h, "1d": df_1d}
) -> dict:
    """
    Score context alignment. For primary e.g. 1H pattern:
      4H bullish -> +15, 1D bullish -> +10 etc.
    Returns dict with per-tf trend and mtf_score (-15 to +25)
    """
    primary_trend = classify_trend(primary_df.row(-1, named=True)) if primary_df.height else "RANGE"
    per_tf = {}
    mtf_score = 0
    for tf, df in higher_dfs.items():
        if df is None or df.height == 0:
            continue
        trend = classify_trend(df.row(-1, named=True))
        per_tf[tf] = trend
        # Alignment: bullish pattern types benefit from bullish higher TF
        # We don't know pattern direction here; caller will adjust.
        # For now, raw: bullish trend = +1, bearish = -1
        if "UPTREND" in trend:
            mtf_score += 10 if tf == "1d" else 15  # 4h heavier if primary 1h
        elif "DOWNTREND" in trend:
            mtf_score -= 10 if tf == "1d" else 15
    return {"primary_trend": primary_trend, "higher_trends": per_tf, "mtf_raw_score": mtf_score}


def mtf_adjusted_score(pattern_type: str, mtf: dict) -> int:
    """Convert raw mtf score to pattern-specific points §33 Trend context 15."""
    # Determine pattern bias
    bullish = pattern_type in ("double_bottom", "inverse_head_shoulders", "falling_wedge", "ascending_triangle")
    bearish = pattern_type in ("double_top", "head_shoulders", "rising_wedge", "descending_triangle")
    # symmetrical triangle is neutral: any trend alignment is partial credit
    raw = mtf.get("mtf_raw_score", 0)
    if pattern_type == "triangle":
        # neutral: trending regime is favorable for breakout quality
        return max(0, min(8, abs(raw) // 3))
    if bullish:
        if raw > 0:
            return min(15, raw)
        else:
            # penalty if higher TF bearish
            return max(-10, raw // 2)
    if bearish:
        if raw < 0:
            return min(15, abs(raw))
        else:
            return max(-10, -raw // 2)
    return 0
