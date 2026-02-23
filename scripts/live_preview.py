"""Live preview server for the MBTA LED matrix renderer."""

from __future__ import annotations

import io
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from PIL import Image

from src.config import load_config
from src.data.mbta_client import MBTAClient
from src.data.poller import MBTAPoller, PollResult
from src.logic.scorer import assess_reliability
from src.rendering import FrameData, TripRow, compose_frame, save_frame

FRAME_PATH = Path("emulator_output/frame.png")


def _parse_time(value: str) -> datetime | None:
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _minutes_away(now: datetime, dt: datetime) -> int:
    return max(int(round((dt - now).total_seconds() / 60.0)), 0)


def _format_clock(dt: datetime) -> str:
    # %-I not supported on all platforms; handle leading zero manually
    value = dt.strftime("%I:%M")
    return value.lstrip("0") if value.startswith("0") else value


def _build_frame_data(result: PollResult) -> tuple[FrameData, list[str]]:
    now = datetime.now()
    assessment = assess_reliability(result)

    trips: list[TripRow] = []
    minutes_debug: list[str] = []

    for pred in result.predictions:
        attrs = pred.get("attributes", {}) if isinstance(pred, dict) else {}
        time_raw = attrs.get("arrival_time") or attrs.get("departure_time")
        if not time_raw:
            continue
        parsed = _parse_time(time_raw)
        if not parsed:
            continue
        minutes = _minutes_away(now, parsed)
        minutes_debug.append(str(minutes))
        trips.append(
            TripRow(
                minutes_away=minutes,
                clock_time=_format_clock(parsed),
                reliability=assessment.classification,
            )
        )
        if len(trips) >= 3:
            break

    data = FrameData(trips=trips, ticker_text=assessment.reason)
    return data, minutes_debug


class PreviewHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"ok")
            return

        if self.path == "/frame.png":
            if not FRAME_PATH.exists():
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(FRAME_PATH.read_bytes())
            return

        if self.path == "/":
            html = """<!doctype html>
<html>
  <head>
    <meta http-equiv="refresh" content="10">
    <style>
      body { background: #111; color: #fff; font-family: sans-serif; }
      img { width: 512px; height: 256px; image-rendering: pixelated; }
    </style>
    <title>MBTA Live Preview</title>
  </head>
  <body>
    <h1>MBTA Live Preview</h1>
    <img src="/frame.png" alt="Frame">
  </body>
</html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        return


def _run_server() -> None:
    server = HTTPServer(("0.0.0.0", 8080), PreviewHandler)
    server.serve_forever()


def main() -> int:
    config = load_config()
    client = MBTAClient(config.mbta.api_key)
    poller = MBTAPoller(
        client=client,
        route_id=config.mbta.route_id,
        stop_id=config.mbta.stop_id,
        direction_id=config.mbta.direction_id,
        poll_interval_seconds=config.mbta.poll_interval_seconds,
    )

    poller.start()

    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()

    try:
        while True:
            result = poller.get_latest()
            if result is None:
                time.sleep(config.mbta.poll_interval_seconds)
                continue

            frame_data, minutes_debug = _build_frame_data(result)
            image = compose_frame(frame_data)
            save_frame(image, str(FRAME_PATH))

            timestamp = datetime.utcnow().isoformat()
            print(
                "preview_update",
                {
                    "timestamp": timestamp,
                    "minutes_away": minutes_debug,
                    "reliability": frame_data.trips[0].reliability if frame_data.trips else "NONE",
                },
                flush=True,
            )

            time.sleep(config.mbta.poll_interval_seconds)
    except KeyboardInterrupt:
        poller.stop()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
