"""Data structures for rendering frames."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TripRow:
    """Single trip cell for display."""

    minutes_away: float
    clock_time: str
    reliability: str
    departed: bool = False
    cancelled: bool = False
    scheduled_only: bool = False
    trend: str = "stable"


@dataclass(frozen=True)
class FrameData:
    """Frame data for the renderer."""

    trips: list[TripRow]  # up to 6 trips
    ticker_text: str


__all__ = ["TripRow", "FrameData"]
