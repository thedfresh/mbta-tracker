from __future__ import annotations

from PIL import Image

from src.logic.scorer import BAD, GOOD, RISKY, UNKNOWN
from src.rendering.composer import (
    COLOR_BAD,
    COLOR_GOOD,
    COLOR_PLACEHOLDER_DOT,
    COLOR_RISKY,
    COLOR_UNKNOWN,
    CELL_HEIGHT,
    CELL_WIDTH,
    DOT_CENTER_OFFSET,
    STATION_HARVARD,
    STATION_SULLIVAN,
    STATION_UNION,
    compose_frame,
)
from src.rendering.frame_data import FrameData, TripRow


def _dot_center(index: int) -> tuple[int, int]:
    col = index % 3
    row = index // 3
    return (
        col * CELL_WIDTH + DOT_CENTER_OFFSET,
        row * CELL_HEIGHT + CELL_HEIGHT // 2,
    )


def test_compose_frame_size_and_mode() -> None:
    data = FrameData(trips=[], ticker_text="Test")
    image = compose_frame(data)
    assert isinstance(image, Image.Image)
    assert image.size == (192, 64)
    assert image.mode == "RGB"


def test_compose_frame_six_trips_dot_colors() -> None:
    data = FrameData(
        trips=[
            TripRow(3, "12:01", GOOD),
            TripRow(7, "12:08", RISKY),
            TripRow(12, "12:15", BAD),
            TripRow(5, "12:20", UNKNOWN),
            TripRow(9, "12:30", GOOD),
            TripRow(14, "12:45", RISKY),
        ],
        ticker_text="All good",
    )
    image = compose_frame(data)
    pixels = image.load()

    assert pixels[_dot_center(0)] == COLOR_GOOD
    assert pixels[_dot_center(1)] == COLOR_RISKY
    assert pixels[_dot_center(2)] == COLOR_BAD
    assert pixels[_dot_center(3)] == COLOR_UNKNOWN
    assert pixels[_dot_center(4)] == COLOR_GOOD
    assert pixels[_dot_center(5)] == COLOR_RISKY


def test_compose_frame_partial_grid_placeholder_cells() -> None:
    data = FrameData(
        trips=[
            TripRow(5, "12:10", GOOD),
            TripRow(7, "12:12", RISKY),
            TripRow(9, "12:14", BAD),
            TripRow(11, "12:16", GOOD),
        ],
        ticker_text="",
    )
    image = compose_frame(data)
    pixels = image.load()

    assert pixels[_dot_center(4)] == COLOR_PLACEHOLDER_DOT
    assert pixels[_dot_center(5)] == COLOR_PLACEHOLDER_DOT


def test_compose_frame_zero_trips_placeholder_rows() -> None:
    data = FrameData(trips=[], ticker_text="")
    image = compose_frame(data)
    pixels = image.load()

    assert pixels[_dot_center(0)] == COLOR_PLACEHOLDER_DOT
    assert pixels[_dot_center(1)] == COLOR_PLACEHOLDER_DOT
    assert pixels[_dot_center(2)] == COLOR_PLACEHOLDER_DOT
    assert pixels[_dot_center(3)] == COLOR_PLACEHOLDER_DOT
    assert pixels[_dot_center(4)] == COLOR_PLACEHOLDER_DOT
    assert pixels[_dot_center(5)] == COLOR_PLACEHOLDER_DOT


def test_compose_frame_reliability_colors() -> None:
    data = FrameData(
        trips=[
            TripRow(1, "12:00", GOOD),
            TripRow(2, "12:02", RISKY),
            TripRow(3, "12:03", UNKNOWN),
        ],
        ticker_text="",
    )
    image = compose_frame(data)
    pixels = image.load()

    assert pixels[_dot_center(0)] == COLOR_GOOD
    assert pixels[_dot_center(1)] == COLOR_RISKY
    assert pixels[_dot_center(2)] == COLOR_UNKNOWN


def test_compose_frame_ticker_smoke() -> None:
    data = FrameData(trips=[TripRow(1, "12:00", GOOD)], ticker_text="Service normal")
    image = compose_frame(data)
    assert image.size == (192, 64)


def test_station_strip_colors() -> None:
    data = FrameData(trips=[], ticker_text="")
    image = compose_frame(data)
    pixels = image.load()

    y = 56
    assert pixels[1, y] == STATION_SULLIVAN
    assert pixels[65, y] == STATION_UNION
    assert pixels[129, y] == STATION_HARVARD


def test_cancelled_trip_smoke() -> None:
    data = FrameData(
        trips=[TripRow(0, "1:45", UNKNOWN, cancelled=True)],
        ticker_text="",
    )
    image = compose_frame(data)
    assert image.size == (192, 64)
