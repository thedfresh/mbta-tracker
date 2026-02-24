"""Frame composer for the LED matrix display."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src.logic.scorer import BAD, GOOD, RISKY, UNKNOWN
from src.rendering.frame_data import FrameData, TripRow

PANEL_WIDTH = 64
TOTAL_PANELS = 3
DISPLAY_WIDTH = PANEL_WIDTH * TOTAL_PANELS
DISPLAY_HEIGHT = 64
DISPLAY_HEIGHT_SMALL = 32

GRID_COLS = 3
GRID_ROWS = 2
CELL_WIDTH = 64
CELL_HEIGHT = 24
TRIP_ZONE_HEIGHT = 48

SEPARATOR_Y = 48
SEPARATOR_COLOR = (42, 42, 42)

STATION_STRIP_TOP = 49
STATION_STRIP_HEIGHT = 15
STATION_BAR_WIDTH = 2

GRID_LINE_COLOR = (15, 15, 15)
GRID_HORIZONTAL = 24

DOT_DIAMETER = 6
DOT_RADIUS = DOT_DIAMETER // 2
DOT_LEFT_MARGIN = 5
DOT_CENTER_OFFSET = DOT_LEFT_MARGIN + DOT_RADIUS

TEXT_LEFT_X = 14
TEXT_GAP = 3

COLOR_TEXT = (255, 255, 255)
COLOR_CLOCK = (136, 136, 136)
COLOR_DIM_TEXT = (48, 48, 48)
COLOR_CLOCK_COMMITTED = (0, 200, 0)

COLOR_GOOD = (0, 200, 0)
COLOR_RISKY = (220, 180, 0)
COLOR_RISKY_DETERIORATING = (230, 140, 0)
COLOR_BAD = (200, 0, 0)
COLOR_UNKNOWN = (72, 72, 72)
COLOR_PLACEHOLDER_DOT = (72, 72, 72)

STATION_SULLIVAN = (232, 119, 34)
STATION_UNION = (0, 132, 61)
STATION_HARVARD = (218, 41, 28)

FONT_REGULAR = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "TerminusTTF-4.49.3.ttf"
FONT_BOLD = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "TerminusTTF-Bold-4.49.3.ttf"
if not FONT_REGULAR.exists():
    raise FileNotFoundError(
        f"Font file not found at {FONT_REGULAR}. "
        "Download TerminusTTF and place it at assets/fonts/TerminusTTF-4.49.3.ttf."
    )
if not FONT_BOLD.exists():
    raise FileNotFoundError(
        f"Font file not found at {FONT_BOLD}. "
        "Download TerminusTTF bold and place it at assets/fonts/TerminusTTF-Bold-4.49.3.ttf."
    )

FONT_MINUTES = ImageFont.truetype(str(FONT_BOLD), 10)
FONT_CLOCK = ImageFont.truetype(str(FONT_REGULAR), 7)
FONT_CANCELLED = ImageFont.truetype(str(FONT_REGULAR), 8)
FONT_STATION = ImageFont.truetype(str(FONT_BOLD), 10)


def _dot_color(reliability: str, trend: str) -> tuple[int, int, int]:
    if reliability == GOOD:
        return COLOR_GOOD
    if reliability == RISKY:
        return COLOR_RISKY_DETERIORATING if trend == "deteriorating" else COLOR_RISKY
    if reliability == BAD:
        return COLOR_BAD
    if reliability == UNKNOWN:
        return COLOR_UNKNOWN
    return COLOR_UNKNOWN


def _draw_trip_cell(
    draw: ImageDraw.ImageDraw,
    index: int,
    trip: TripRow | None,
    grid_cols: int,
    cell_width: int,
    cell_height: int,
) -> None:
    col = index % grid_cols
    row = index // grid_cols
    cell_left = col * cell_width
    cell_top = row * cell_height

    dot_top = cell_top + (cell_height - DOT_DIAMETER) // 2
    dot_left = cell_left + DOT_LEFT_MARGIN
    dot_right = dot_left + DOT_DIAMETER - 1
    dot_bottom = dot_top + DOT_DIAMETER - 1

    if trip is None:
        dot_color = COLOR_PLACEHOLDER_DOT
        text = "--"
        text_color = COLOR_DIM_TEXT
        text_font = FONT_CANCELLED
        bbox = draw.textbbox((0, 0), text, font=text_font)
        text_height = bbox[3] - bbox[1]
        text_y = cell_top + (cell_height - text_height) // 2
        draw.ellipse([dot_left, dot_top, dot_right, dot_bottom], fill=dot_color)
        draw.text((cell_left + TEXT_LEFT_X, text_y), text, font=text_font, fill=text_color)
        return

    if trip.cancelled:
        dot_color = COLOR_UNKNOWN
        text = trip.clock_time or "CNCLD"
        text_color = COLOR_DIM_TEXT
        bbox = draw.textbbox((0, 0), text, font=FONT_CANCELLED)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = cell_left + TEXT_LEFT_X
        text_y = cell_top + (cell_height - text_height) // 2
        draw.ellipse([dot_left, dot_top, dot_right, dot_bottom], fill=dot_color)
        draw.text((text_x, text_y), text, font=FONT_CANCELLED, fill=text_color)
        strike_y = text_y + text_height // 2
        draw.line(
            (text_x, strike_y, text_x + text_width, strike_y),
            fill=text_color,
            width=1,
        )
        return

    dot_color = COLOR_GOOD if trip.departed else _dot_color(trip.reliability, trip.trend)
    minutes_text = "NOW" if trip.minutes_away < 1.0 else f"{round(trip.minutes_away)}m"
    minutes_bbox = draw.textbbox((0, 0), minutes_text, font=FONT_MINUTES)
    minutes_width = minutes_bbox[2] - minutes_bbox[0]
    minutes_height = minutes_bbox[3] - minutes_bbox[1]
    minutes_y = cell_top + (cell_height - minutes_height) // 2
    minutes_x = cell_left + TEXT_LEFT_X
    minutes_color = COLOR_GOOD if trip.departed else COLOR_TEXT

    clock_text = trip.clock_time
    clock_bbox = draw.textbbox((0, 0), clock_text, font=FONT_CLOCK)
    clock_height = clock_bbox[3] - clock_bbox[1]
    clock_x = minutes_x + minutes_width + TEXT_GAP
    clock_y = cell_top + (cell_height - clock_height) // 2
    clock_color = COLOR_CLOCK_COMMITTED if trip.departed else COLOR_CLOCK

    draw.ellipse([dot_left, dot_top, dot_right, dot_bottom], fill=dot_color)
    draw.text((minutes_x, minutes_y), minutes_text, font=FONT_MINUTES, fill=minutes_color)
    draw.text((clock_x, clock_y), clock_text, font=FONT_CLOCK, fill=clock_color)


def compose_frame(data: FrameData, width: int = DISPLAY_WIDTH, height: int = DISPLAY_HEIGHT) -> Image.Image:
    """Compose an RGB frame from FrameData for 32px or 64px tall panel chains."""
    if width % PANEL_WIDTH != 0:
        raise ValueError(f"Width must be a multiple of {PANEL_WIDTH}, got {width}.")
    if height not in (DISPLAY_HEIGHT_SMALL, DISPLAY_HEIGHT):
        raise ValueError(
            f"Height must be {DISPLAY_HEIGHT_SMALL} or {DISPLAY_HEIGHT}, got {height}."
        )

    grid_cols = width // PANEL_WIDTH
    # For 2x64x64 setup, favor readability over density: one large row (2 trips).
    if width == 128 and height == DISPLAY_HEIGHT:
        grid_rows = 1
        cell_height = 48
    else:
        grid_rows = 2 if height == DISPLAY_HEIGHT else 1
        cell_height = 24 if grid_rows == 2 else height
    trip_zone_height = grid_rows * cell_height
    image = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(image)

    trips = list(data.trips)[: grid_cols * grid_rows]
    for idx in range(grid_cols * grid_rows):
        trip = trips[idx] if idx < len(trips) else None
        _draw_trip_cell(draw, idx, trip, grid_cols, PANEL_WIDTH, cell_height)

    for x in range(PANEL_WIDTH, width, PANEL_WIDTH):
        draw.line((x, 0, x, trip_zone_height - 1), fill=GRID_LINE_COLOR)
    if grid_rows == 2:
        draw.line((0, GRID_HORIZONTAL, width - 1, GRID_HORIZONTAL), fill=GRID_LINE_COLOR)
        draw.line((0, SEPARATOR_Y, width - 1, SEPARATOR_Y), fill=SEPARATOR_COLOR)

    stations = [
        (STATION_SULLIVAN, "12m"),
        (STATION_UNION, "18m"),
        (STATION_HARVARD, "28m"),
    ]
    if height == DISPLAY_HEIGHT:
        station_blocks = stations[:grid_cols]
        for idx, (color, label) in enumerate(station_blocks):
            block_left = idx * PANEL_WIDTH
            bar_right = block_left + STATION_BAR_WIDTH - 1
            draw.rectangle(
                (block_left, STATION_STRIP_TOP, bar_right, height - 1),
                fill=color,
            )

            text_bbox = draw.textbbox((0, 0), label, font=FONT_STATION)
            text_height = text_bbox[3] - text_bbox[1]
            text_y = STATION_STRIP_TOP + (STATION_STRIP_HEIGHT - text_height) // 2
            text_x = block_left + STATION_BAR_WIDTH + 2
            draw.text((text_x, text_y), label, font=FONT_STATION, fill=color)

    return image


__all__ = ["compose_frame"]
