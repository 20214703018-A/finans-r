"""Simple APScheduler §38 – cron-like without Redis/Celery."""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.config import settings
from app.pipeline import analyze_asset
import logging

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()

# Track last results in memory (MVP – no Redis)
last_scan_results: dict = {}


async def _job_for_timeframe(timeframe: str):
    symbols = settings.crypto_symbols
    logger.info(f"[scheduler] scan {timeframe} for {symbols}")
    for sym in symbols:
        try:
            res = await analyze_asset(sym, timeframe, limit=300, include_reasoning=False)
            last_scan_results[f"{sym}:{timeframe}"] = res
        except Exception as e:
            logger.warning(f"scan failed {sym} {timeframe}: {e}")


def start_scheduler():
    # 15m every 15 min, 1h hourly, 4h every 4h, 1d daily
    scheduler.add_job(lambda: _job_for_timeframe("15m"), IntervalTrigger(minutes=15), id="scan_15m", replace_existing=True)
    scheduler.add_job(lambda: _job_for_timeframe("1h"), IntervalTrigger(hours=1), id="scan_1h", replace_existing=True)
    scheduler.add_job(lambda: _job_for_timeframe("4h"), IntervalTrigger(hours=4), id="scan_4h", replace_existing=True)
    scheduler.add_job(lambda: _job_for_timeframe("1d"), IntervalTrigger(hours=24), id="scan_1d", replace_existing=True)
    scheduler.start()
    logger.info("APScheduler started")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
