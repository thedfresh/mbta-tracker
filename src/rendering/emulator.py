"""Frame output helpers for the LED matrix emulator."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


def save_frame(image: Image.Image, path: str = "emulator_output/frame.png") -> None:
    """Save a frame to disk as a PNG image."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")


__all__ = ["save_frame"]
