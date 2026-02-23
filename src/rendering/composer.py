"""Frame composer for the LED matrix display."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src.logic.scorer import BAD, GOOD, RISKY, UNKNOWN
from src.rendering.frame_data import FrameData, TripRow

DISPLAY_WIDTH = 128
DISPLAY_HEIGHT = 64

TRIP_ZONE_HEIGHT = 42
TRIP_ROW_HEIGHT = 14
TRIP_ROW_COUNT = 3
SEPARATOR_Y = 42
SEPARATOR_COLOR = (51, 51, 51)

TICKER_TOP = 43
TICKER_HEIGHT = 21

DOT_DIAMETER = 8
DOT_RADIUS = DOT_DIAMETER // 2
DOT_LEFT_MARGIN = 3
DOT_CENTER_X = DOT_LEFT_MARGIN + DOT_RADIUS

TEXT_LEFT_X = 16

COLOR_TEXT = (255, 255, 255)
COLOR_PLACEHOLDER_TEXT = (60, 60, 60)

COLOR_GOOD = (0, 200, 0)
COLOR_RISKY = (220, 180, 0)
COLOR_BAD = (200, 0, 0)
COLOR_UNKNOWN = (80, 80, 80)
COLOR_PLACEHOLDER_DOT = (80, 80, 80)

FONT_PATH = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "TerminusTTF-4.49.3.ttf"
if not FONT_PATH.exists():
    raise FileNotFoundError(
        f"Font file not found at {FONT_PATH}. "
        "Download TerminusTTF and place it at assets/fonts/TerminusTTF-4.49.3.ttf."
    )

FONT_TRIP = ImageFont.truetype(str(FONT_PATH), 11)
FONT_TICKER = ImageFont.truetype(str(FONT_PATH), 10)


def _dot_color(reliability: str) -> tuple[int, int, int]:
    if reliability == GOOD:
        return COLOR_GOOD
    if reliability == RISKY:
        return COLOR_RISKY
    if reliability == BAD:
        return COLOR_BAD
    if reliability == UNKNOWN:
        return COLOR_UNKNOWN
    return COLOR_UNKNOWN


def _draw_trip_row(draw: ImageDraw.ImageDraw, row_index: int, trip: TripRow | None) -> None:
    row_top = row_index * TRIP_ROW_HEIGHT
    dot_top = row_top + (TRIP_ROW_HEIGHT - DOT_DIAMETER) // 2
    dot_left = DOT_LEFT_MARGIN
    dot_right = dot_left + DOT_DIAMETER - 1
    dot_bottom = dot_top + DOT_DIAMETER - 1

    if trip is None:
        dot_color = COLOR_PLACEHOLDER_DOT
        text_color = COLOR_PLACEHOLDER_TEXT
        text = "--"
    else:
        dot_color = _dot_color(trip.reliability)
        text_color = COLOR_TEXT
        text = f"{trip.minutes_away} min  {trip.clock_time}"

    draw.ellipse([dot_left, dot_top, dot_right, dot_bottom], fill=dot_color)
    draw.text((TEXT_LEFT_X, row_top + 1), text, font=FONT_TRIP, fill=text_color)


def compose_frame(data: FrameData) -> Image.Image:
    """Compose a 128x64 RGB frame from FrameData."""
    image = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(image)

    trips = list(data.trips)[:TRIP_ROW_COUNT]
    for idx in range(TRIP_ROW_COUNT):
        trip = trips[idx] if idx < len(trips) else None
        _draw_trip_row(draw, idx, trip)

    draw.line((0, SEPARATOR_Y, DISPLAY_WIDTH - 1, SEPARATOR_Y), fill=SEPARATOR_COLOR)

    ticker_text = data.ticker_text or ""
    bbox = draw.textbbox((0, 0), ticker_text, font=FONT_TICKER)
    text_height = bbox[3] - bbox[1]
    ticker_y = TICKER_TOP + (TICKER_HEIGHT - text_height) // 2
    draw.text((DOT_LEFT_MARGIN, ticker_y), ticker_text, font=FONT_TICKER, fill=COLOR_TEXT)

    return image


__all__ = ["compose_frame"]
