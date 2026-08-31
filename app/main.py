from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager
from pathlib import Path
from app.config import settings
from app.api.assets import router as assets_router
from app.api.analyze import router as analyze_router
from app.db.session import init_db
from app.db.seed import seed_assets
from app.scheduler import start_scheduler, stop_scheduler
from app.engine.signal_fusion_v2 import SignalFusionEngine
from app.engine.risk_manager import RiskManager
import logging
import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize engines
fusion_engine = SignalFusionEngine()
risk_manager = RiskManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        await init_db()
        await seed_assets()
        logger.info("DB initialized and seeded")
    except Exception as e:
        logger.warning(f"DB init failed (will run without DB): {e}")
    # Scheduler only if not in test env
    if settings.app_env != "test":
        try:
            start_scheduler()
        except Exception as e:
            logger.warning(f"scheduler failed: {e}")
    yield
    # Shutdown
    try:
        stop_scheduler()
    except Exception:
        pass


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AI Market Pattern Scanner – MVP. Sayısal motor önce, YOLO ikinci görüş, LLM açıklama katmanı.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assets_router)
app.include_router(analyze_router)

# frontend static
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def root():
    # serve UI if exists, else JSON
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": ["/assets", "/assets/timeframes", "/assets/patterns", "/assets/yolo/status", "/analyze", "/scan", "/backtest", "/chart", "/yolo/preview"],
    }


@app.get("/app")
async def app_ui():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"detail": "frontend not built"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/analyze-full")
async def analyze_full(
    symbol: str = Query(..., description="Symbol to analyze (e.g., BTCUSD, AAPL)"),
    timeframe: str = Query("1h", description="Timeframe: 1m, 5m, 15m, 1h, 4h, 1d, 1w")
):
    """
    Full Signal Fusion Analysis with Multi-Timeframe Alignment
    
    Uses ALL 44 indicators with adaptive weighting based on timeframe.
    Returns detailed sensor votes, conflicts, MTF alignment, and strategy mode.
    """
    try:
        # Fetch data using pipeline's provider system
        from app.providers import get_provider_for_symbol
        from app.data.normalize import bars_to_df, normalize
        from app.indicators import calculate_indicators
        
        provider = get_provider_for_symbol(symbol)
        bars = await provider.get_bars(symbol=symbol, timeframe=timeframe, limit=300)
        
        if not bars or len(bars) < 50:
            return JSONResponse(status_code=400, content={"error": "Yetersiz veri"})
        
        df_pl = bars_to_df(bars)
        df_pl = normalize(df_pl)
        df_pl = calculate_indicators(df_pl)
        
        # Convert polars to pandas for fusion engine
        df = df_pl.to_pandas()
        current_price = float(df['close'].iloc[-1])
        
        # Fetch higher timeframe data for MTF analysis
        tf_map = {'1m': '5m', '5m': '15m', '15m': '1h', '1h': '4h', '4h': '1d', '1d': '1w', '1w': '1M'}
        higher_tf = tf_map.get(timeframe, '4h')
        daily_tf = '1d' if timeframe not in ['1d', '1w'] else '1M'
        
        higher_bars = await provider.get_bars(symbol=symbol, timeframe=higher_tf, limit=300)
        daily_bars = await provider.get_bars(symbol=symbol, timeframe=daily_tf, limit=300)
        
        higher_df = None
        daily_df = None
        
        if higher_bars and len(higher_bars) >= 50:
            higher_pl = bars_to_df(higher_bars)
            higher_pl = normalize(higher_pl)
            higher_pl = calculate_indicators(higher_pl)
            higher_df = higher_pl.to_pandas()
            
        if daily_bars and len(daily_bars) >= 50:
            daily_pl = bars_to_df(daily_bars)
            daily_pl = normalize(daily_pl)
            daily_pl = calculate_indicators(daily_pl)
            daily_df = daily_pl.to_pandas()
        
        # Run fusion analysis
        result = fusion_engine.analyze(
            df=df,
            current_price=current_price,
            symbol=symbol,
            timeframe=timeframe,
            higher_tf_data=higher_df,
            daily_data=daily_df
        )
        
        # Convert to JSON-serializable format
        response = {
            "symbol": symbol,
            "timeframe": timeframe,
            "current_price": current_price,
            "signal": result.signal.value,
            "score": round(result.total_score, 2),
            "strategy": result.strategy_mode.value,
            "confidence": round(result.confidence, 3),
            "votes": [
                {
                    "sensor": v.name,
                    "vote": v.vote,
                    "weight": v.weight,
                    "reason": v.reason,
                    "indicator": v.indicator_used
                }
                for v in result.votes
            ],
            "mtf_alignment": result.mtf_alignment,
            "conflicts": result.conflicts,
            "used_indicators": result.timeframe_optimized_indicators,
            "pattern_context": result.pattern_context,
            "timestamp": pd.Timestamp.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Fusion analysis error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})
