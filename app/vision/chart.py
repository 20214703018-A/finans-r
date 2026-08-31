"""Chart Renderer §31 – 1280x720, 120 candles, no indicators/text."""
import polars as pl
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mplfinance as mpf
import io
import pandas as pd


def render_chart(df: pl.DataFrame, width: int = 1280, height: int = 720, candles: int = 120) -> bytes:
    """
    Returns PNG bytes. Standard: 1280x720, 120 candles, same candle style, no indicators.
    """
    # Take last 120 candles
    df = df.tail(candles)
    # Convert to pandas with DatetimeIndex for mplfinance
    pdf = df.to_pandas()
    # Ensure timestamp is datetime
    if "timestamp" not in pdf.columns:
        raise ValueError("timestamp column missing")
    pdf["Date"] = pd.to_datetime(pdf["timestamp"], utc=True)
    pdf = pdf.set_index("Date")
    # mplfinance expects columns Open, High, Low, Close, Volume capitalized
    pdf = pdf.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})

    # Style: classic, no volume, no mav
    style = mpf.make_mpf_style(base_mpf_style="yahoo", gridstyle="", y_on_right=False)

    dpi = 100
    fig_w = width / dpi
    fig_h = height / dpi
    fig, axes = mpf.plot(
        pdf,
        type="candle",
        style=style,
        volume=False,
        returnfig=True,
        figsize=(fig_w, fig_h),
        tight_layout=True,
        xrotation=0,
        datetime_format="%m-%d",
        show_nontrading=False,
    )
    # Remove axis labels/text for YOLO purity §31 no text/drawings
    for ax in axes:
        ax.set_xlabel("")
        ax.set_ylabel("")
        ax.set_title("")
        # hide x tick labels to avoid text variance
        ax.set_xticklabels([])
        ax.tick_params(labelbottom=False)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def save_chart_png(df: pl.DataFrame, path: str) -> str:
    data = render_chart(df)
    with open(path, "wb") as f:
        f.write(data)
    return path
