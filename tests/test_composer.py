from __future__ import annotations

from PIL import Image

from src.logic.scorer import BAD, GOOD, RISKY, UNKNOWN
from src.rendering.composer import (
    COLOR_BAD,
    COLOR_GOOD,
    COLOR_PLACEHOLDER_DOT,
    COLOR_RISKY,
    COLOR_UNKNOWN,
    DOT_CENTER_X,
    TRIP_ROW_HEIGHT,
    compose_frame,
)
from src.rendering.frame_data import FrameData, TripRow


def _dot_center(row_index: int) -> tuple[int, int]:
    return DOT_CENTER_X, row_index * TRIP_ROW_HEIGHT + TRIP_ROW_HEIGHT // 2


def test_compose_frame_size_and_mode() -> None:
    data = FrameData(trips=[], ticker_text="Test")
    image = compose_frame(data)
    assert isinstance(image, Image.Image)
    assert image.size == (192, 64)
    assert image.mode == "RGB"


def test_compose_frame_three_trips_dot_colors() -> None:
    data = FrameData(
        trips=[
            TripRow(3, "12:01", GOOD),
            TripRow(7, "12:08", RISKY),
            TripRow(12, "12:15", BAD),
        ],
        ticker_text="All good",
    )
    image = compose_frame(data)
    pixels = image.load()

    assert pixels[_dot_center(0)] == COLOR_GOOD
    assert pixels[_dot_center(1)] == COLOR_RISKY
    assert pixels[_dot_center(2)] == COLOR_BAD


def test_compose_frame_one_trip_placeholder_rows() -> None:
    data = FrameData(trips=[TripRow(5, "12:10", GOOD)], ticker_text="")
    image = compose_frame(data)
    pixels = image.load()

    assert pixels[_dot_center(1)] == COLOR_PLACEHOLDER_DOT
    assert pixels[_dot_center(2)] == COLOR_PLACEHOLDER_DOT


def test_compose_frame_zero_trips_placeholder_rows() -> None:
    data = FrameData(trips=[], ticker_text="")
    image = compose_frame(data)
    pixels = image.load()

    assert pixels[_dot_center(0)] == COLOR_PLACEHOLDER_DOT
    assert pixels[_dot_center(1)] == COLOR_PLACEHOLDER_DOT
    assert pixels[_dot_center(2)] == COLOR_PLACEHOLDER_DOT


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


def test_compose_frame_right_panel_black() -> None:
    data = FrameData(trips=[TripRow(2, "12:05", GOOD)], ticker_text="Right panel")
    image = compose_frame(data)
    pixels = image.load()

    sample_x = [140, 160, 180]
    sample_y = [0, 10, 20, 30, 40, 50, 63]
    for x in sample_x:
        for y in sample_y:
            assert pixels[x, y] == (0, 0, 0)
