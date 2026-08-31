from datetime import datetime, timezone
from sqlalchemy import (
    String,
    Float,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
    Text,
    Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum


class Base(DeclarativeBase):
    pass


def utcnow():
    return datetime.now(timezone.utc)


class AssetType(str, enum.Enum):
    crypto = "crypto"
    equity_us = "equity_us"
    equity_tr = "equity_tr"


class PatternType(str, enum.Enum):
    double_top = "double_top"
    double_bottom = "double_bottom"
    head_shoulders = "head_shoulders"
    inverse_head_shoulders = "inverse_head_shoulders"
    triangle = "triangle"
    ascending_triangle = "ascending_triangle"
    descending_triangle = "descending_triangle"
    rising_wedge = "rising_wedge"
    falling_wedge = "falling_wedge"


class PatternStatus(str, enum.Enum):
    forming = "forming"
    mature = "mature"
    breakout_pending = "breakout_pending"
    confirmed = "confirmed"
    failed = "failed"
    invalidated = "invalidated"


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # e.g. BTCUSD.KRAKEN
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    mic: Mapped[str | None] = mapped_column(String(16), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    currency: Mapped[str] = mapped_column(String(16), nullable=False, default="USD")
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False, default=AssetType.crypto.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    candles: Mapped[list["Candle"]] = relationship(back_populates="asset")
    patterns: Mapped[list["Pattern"]] = relationship(back_populates="asset")


class Candle(Base):
    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint("asset_id", "timeframe", "timestamp", name="uq_candle_asset_tf_ts"),
        Index("ix_candles_asset_tf_ts", "asset_id", "timeframe", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("assets.id"), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)

    asset: Mapped[Asset] = relationship(back_populates="candles")


class Pattern(Base):
    __tablename__ = "patterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("assets.id"), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    pattern_type: Mapped[str] = mapped_column(String(64), nullable=False)

    geometry_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    breakout_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    trend_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    momentum_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    yolo_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    support_resistance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=PatternStatus.forming.value)

    details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    yolo_pattern: Mapped[str | None] = mapped_column(String(64), nullable=True)
    yolo_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # anchors for explainability
    neckline: Mapped[float | None] = mapped_column(Float, nullable=True)
    invalidation_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    asset: Mapped[Asset] = relationship(back_populates="patterns")


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("assets.id"), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_analyses_asset_tf_created", "asset_id", "timeframe", "created_at"),)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("assets.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("user_id", "asset_id", name="uq_watchlist_user_asset"),)
