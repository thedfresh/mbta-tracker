"""Data structures for rendering frames."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TripRow:
    """Single trip cell for display."""

    minutes_away: int
    clock_time: str
    reliability: str
    departed: bool = False
    cancelled: bool = False
    scheduled_only: bool = False


@dataclass(frozen=True)
class FrameData:
    """Frame data for the renderer."""

    trips: list[TripRow]  # up to 6 trips
    ticker_text: str


__all__ = ["TripRow", "FrameData"]
