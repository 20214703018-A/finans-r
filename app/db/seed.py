"""Seed assets table with MVP universe."""
from sqlalchemy import select
from app.db.session import async_session
from app.db.models import Asset, AssetType

DEFAULT_ASSETS = [
    # Crypto – Kraken
    ("BTCUSD.KRAKEN", "BTCUSD", "KRAKEN", "XKRA", "UTC", "USD", AssetType.crypto.value),
    ("ETHUSD.KRAKEN", "ETHUSD", "KRAKEN", "XKRA", "UTC", "USD", AssetType.crypto.value),
    ("SOLUSD.KRAKEN", "SOLUSD", "KRAKEN", "XKRA", "UTC", "USD", AssetType.crypto.value),
    ("XRPUSD.KRAKEN", "XRPUSD", "KRAKEN", "XKRA", "UTC", "USD", AssetType.crypto.value),
    ("BNBUSD.KRAKEN", "BNBUSD", "KRAKEN", "XKRA", "UTC", "USD", AssetType.crypto.value),
    ("DOGEUSD.KRAKEN", "DOGEUSD", "KRAKEN", "XKRA", "UTC", "USD", AssetType.crypto.value),
    ("ADAUSD.KRAKEN", "ADAUSD", "KRAKEN", "XKRA", "UTC", "USD", AssetType.crypto.value),
    ("AVAXUSD.KRAKEN", "AVAXUSD", "KRAKEN", "XKRA", "UTC", "USD", AssetType.crypto.value),
    ("LINKUSD.KRAKEN", "LINKUSD", "KRAKEN", "XKRA", "UTC", "USD", AssetType.crypto.value),
    ("SUIUSD.KRAKEN", "SUIUSD", "KRAKEN", "XKRA", "UTC", "USD", AssetType.crypto.value),
    # Nasdaq – Alpaca (placeholder, consolidated feed recommended for prod)
    ("AAPL.XNAS", "AAPL", "ALPACA", "XNAS", "America/New_York", "USD", AssetType.equity_us.value),
    ("MSFT.XNAS", "MSFT", "ALPACA", "XNAS", "America/New_York", "USD", AssetType.equity_us.value),
    ("NVDA.XNAS", "NVDA", "ALPACA", "XNAS", "America/New_York", "USD", AssetType.equity_us.value),
    ("TSLA.XNAS", "TSLA", "ALPACA", "XNAS", "America/New_York", "USD", AssetType.equity_us.value),
    # BIST
    ("THYAO.XIST", "THYAO", "BIST", "XIST", "Europe/Istanbul", "TRY", AssetType.equity_tr.value),
    ("GARAN.XIST", "GARAN", "BIST", "XIST", "Europe/Istanbul", "TRY", AssetType.equity_tr.value),
    ("AKBNK.XIST", "AKBNK", "BIST", "XIST", "Europe/Istanbul", "TRY", AssetType.equity_tr.value),
]


async def seed_assets():
    async with async_session() as session:
        for asset_id, symbol, exchange, mic, tz, ccy, atype in DEFAULT_ASSETS:
            exists = await session.get(Asset, asset_id)
            if exists is None:
                session.add(
                    Asset(
                        id=asset_id,
                        symbol=symbol,
                        exchange=exchange,
                        mic=mic,
                        timezone=tz,
                        currency=ccy,
                        asset_type=atype,
                        is_active=True,
                    )
                )
        await session.commit()
