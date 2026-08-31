from pydantic import BaseModel, Field
from typing import Literal

Timeframe = Literal["15m", "1h", "4h", "1d"]


class AnalyzeRequest(BaseModel):
    symbol: str = Field(..., examples=["BTCUSD"])
    timeframe: Timeframe = Field(..., examples=["4h"])
    limit: int = Field(default=300, ge=50, le=1000)
    include_reasoning: bool = Field(default=True)


class ScanRequest(BaseModel):
    symbols: list[str] = Field(..., examples=[["BTCUSD", "ETHUSD", "SOLUSD"]])
    timeframe: Timeframe = Field(..., examples=["4h"])
    limit: int = Field(default=300, ge=50, le=1000)
    min_score: float = Field(default=70, ge=0, le=100, description="Only return patterns >= min_score (default 70 watch+ to avoid forced low-quality)")
    include_weak: bool = Field(default=False, description="If true, also return weak (60-69) for debugging")
