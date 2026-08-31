from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from pathlib import Path
from app.config import settings
from app.api.assets import router as assets_router
from app.api.analyze import router as analyze_router
from app.db.session import init_db
from app.db.seed import seed_assets
from app.scheduler import start_scheduler, stop_scheduler
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
