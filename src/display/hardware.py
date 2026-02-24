"""Hardware output driver for HUB75 panels via Piomatter."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class MatrixGeometry:
    """Logical geometry used for panel chain setup."""

    width: int
    height: int
    panel_width: int = 64
    panel_height: int = 64
    n_addr_lines: int | None = None


class MatrixDisplay:
    """Render PIL RGB frames to a chained HUB75 panel setup."""

    def __init__(self, geometry: MatrixGeometry, brightness: int = 80) -> None:
        try:
            import numpy as np
            import adafruit_blinka_raspberry_pi5_piomatter as piomatter
        except ImportError as exc:
            raise RuntimeError(
                "Hardware display requires 'numpy' and "
                "'adafruit_blinka_raspberry_pi5_piomatter' on Raspberry Pi."
            ) from exc

        if geometry.width % geometry.panel_width != 0:
            raise ValueError(
                f"Display width ({geometry.width}) must be a multiple of panel width "
                f"({geometry.panel_width})."
            )
        if geometry.height % geometry.panel_height != 0:
            raise ValueError(
                f"Display height ({geometry.height}) must be a multiple of panel height "
                f"({geometry.panel_height})."
            )

        self._np = np
        self._geometry = geometry
        self._panel_count = geometry.width // geometry.panel_width

        n_addr_lines = geometry.n_addr_lines
        if n_addr_lines is None:
            if geometry.panel_height == 16:
                n_addr_lines = 3
            elif geometry.panel_height == 32:
                n_addr_lines = 4
            elif geometry.panel_height == 64:
                n_addr_lines = 5
            else:
                raise ValueError(
                    "Unsupported panel_height for automatic address-line detection. "
                    "Use 16, 32, or 64, or set n_addr_lines explicitly."
                )

        piomatter_geometry = piomatter.Geometry(
            width=geometry.width,
            height=geometry.height,
            n_addr_lines=n_addr_lines,
            rotation=piomatter.Orientation.Normal,
        )
        self._framebuffer = np.zeros((geometry.height, geometry.width, 3), dtype=np.uint8)
        matrix_kwargs = {
            "colorspace": piomatter.Colorspace.RGB888Packed,
            "pinout": piomatter.Pinout.AdafruitMatrixBonnet,
            "framebuffer": self._framebuffer,
            "geometry": piomatter_geometry,
        }
        try:
            # Newer builds support queue_depth; older builds do not.
            self._matrix = piomatter.PioMatter(**matrix_kwargs, queue_depth=2)
        except TypeError:
            self._matrix = piomatter.PioMatter(**matrix_kwargs)

        # Brightness support may vary by library version.
        if hasattr(self._matrix, "brightness"):
            try:
                self._matrix.brightness = max(0.0, min(1.0, brightness / 100.0))
            except Exception:
                pass

    @property
    def panel_count(self) -> int:
        return self._panel_count

    def render(self, image: Image.Image) -> None:
        """Blit an RGB image to the matrix and flush."""
        if image.size != (self._geometry.width, self._geometry.height):
            raise ValueError(
                "Frame size mismatch. "
                f"Expected {(self._geometry.width, self._geometry.height)}, got {image.size}."
            )

        rgb = image.convert("RGB")
        self._framebuffer[:] = self._np.asarray(rgb, dtype=self._np.uint8)
        self._matrix.show()


__all__ = ["MatrixDisplay", "MatrixGeometry"]
