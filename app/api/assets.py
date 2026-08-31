from fastapi import APIRouter
from sqlalchemy import select
from app.db.session import async_session
from app.db.models import Asset
from app.config import settings

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("")
async def list_assets():
    # Try DB first, fallback to config
    try:
        async with async_session() as session:
            result = await session.execute(select(Asset))
            assets = result.scalars().all()
            if assets:
                return [
                    {
                        "id": a.id,
                        "symbol": a.symbol,
                        "exchange": a.exchange,
                        "mic": a.mic,
                        "timezone": a.timezone,
                        "currency": a.currency,
                        "asset_type": a.asset_type,
                        "is_active": a.is_active,
                    }
                    for a in assets
                ]
    except Exception:
        pass
    # fallback – derive from settings
    fallback = []
    for sym in settings.crypto_symbols + ["AAPL", "MSFT", "NVDA", "TSLA", "THYAO", "GARAN", "AKBNK"]:
        # determine exchange
        if sym.endswith("USD"):
            fallback.append({"id": f"{sym}.KRAKEN", "symbol": sym, "exchange": "KRAKEN", "mic": "XKRA", "timezone": "UTC", "currency": "USD", "asset_type": "crypto", "is_active": True})
        elif sym in ("AAPL", "MSFT", "NVDA", "TSLA"):
            fallback.append({"id": f"{sym}.XNAS", "symbol": sym, "exchange": "ALPACA", "mic": "XNAS", "timezone": "America/New_York", "currency": "USD", "asset_type": "equity_us", "is_active": True})
        else:
            fallback.append({"id": f"{sym}.XIST", "symbol": sym, "exchange": "BIST", "mic": "XIST", "timezone": "Europe/Istanbul", "currency": "TRY", "asset_type": "equity_tr", "is_active": True})
    return fallback


@router.get("/timeframes")
async def list_timeframes():
    return [{"id": k, "minutes": v} for k, v in settings.timeframes.items()]


@router.get("/patterns")
async def list_pattern_types():
    return [
        "double_top",
        "double_bottom",
        "head_shoulders",
        "inverse_head_shoulders",
        "triangle",
        "ascending_triangle",
        "descending_triangle",
        "rising_wedge",
        "falling_wedge",
    ]


@router.get("/yolo/status")
async def yolo_status():
    from app.vision.yolo import get_yolo_engine
    return get_yolo_engine().get_model_info()


@router.post("/yolo/reload")
async def yolo_reload():
    from app.vision.yolo import get_yolo_engine
    eng = get_yolo_engine()
    eng.reload()
    return eng.get_model_info()
