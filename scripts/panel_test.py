"""Panel-chain hardware test for HUB75 displays."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.display import MatrixDisplay, MatrixGeometry


def _build_panel_swatch(width: int, height: int, panel_width: int, panel_count: int) -> Image.Image:
    image = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(image)

    colors = [
        (255, 0, 0),
        (0, 255, 0),
        (0, 0, 255),
        (255, 255, 0),
    ]
    for idx in range(panel_count):
        left = idx * panel_width
        right = left + panel_width - 1
        draw.rectangle((left, 0, right, height - 1), fill=colors[idx % len(colors)])

    return image


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, default=192)
    parser.add_argument("--height", type=int, default=64)
    parser.add_argument("--panel-width", type=int, default=64)
    parser.add_argument("--panel-height", type=int, default=64)
    parser.add_argument("--n-addr-lines", type=int, default=None)
    parser.add_argument("--brightness", type=int, default=80)
    parser.add_argument("--hold-seconds", type=float, default=8.0)
    args = parser.parse_args()

    if args.width % args.panel_width != 0:
        raise SystemExit("--width must be divisible by --panel-width")
    if args.height % args.panel_height != 0:
        raise SystemExit("--height must be divisible by --panel-height")

    panel_count = args.width // args.panel_width
    matrix = MatrixDisplay(
        MatrixGeometry(
            width=args.width,
            height=args.height,
            panel_width=args.panel_width,
            panel_height=args.panel_height,
            n_addr_lines=args.n_addr_lines,
        ),
        brightness=args.brightness,
    )

    print("panel_test_start", {"panel_count": panel_count}, flush=True)
    frame = _build_panel_swatch(args.width, args.height, args.panel_width, panel_count)
    matrix.render(frame)
    time.sleep(args.hold_seconds)

    black = Image.new("RGB", (args.width, args.height), (0, 0, 0))
    matrix.render(black)
    print("panel_test_done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
