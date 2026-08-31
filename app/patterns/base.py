from dataclasses import dataclass, field
from typing import Literal

PatternStatus = Literal["forming", "mature", "breakout_pending", "confirmed", "failed", "invalidated"]


@dataclass
class PatternCandidate:
    pattern_type: str  # e.g. double_top
    status: str
    geometry_score: float  # 0-1
    indices: dict  # e.g. {"peak1": 12, "valley": 18, "peak2": 24}
    prices: dict   # e.g. {"peak1": 112000, "valley": 110500, "peak2": 111800}
    neckline: float | None = None
    invalidation: float | None = None
    target: float | None = None
    breakout: dict = field(default_factory=dict)
    volume: dict = field(default_factory=dict)
    trend: dict = field(default_factory=dict)
    regime: str | None = None
    yolo: dict = field(default_factory=dict)
    support_resistance: dict = field(default_factory=dict)
    # scoring breakdown 0-100
    scores: dict = field(default_factory=dict)
    final_score: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "pattern_type": self.pattern_type,
            "status": self.status,
            "geometry_score": self.geometry_score,
            "indices": self.indices,
            "prices": self.prices,
            "neckline": self.neckline,
            "invalidation": self.invalidation,
            "target": self.target,
            "breakout": self.breakout,
            "volume": self.volume,
            "trend": self.trend,
            "regime": self.regime,
            "yolo": self.yolo,
            "support_resistance": self.support_resistance,
            "scores": self.scores,
            "final_score": self.final_score,
            "notes": self.notes,
        }
