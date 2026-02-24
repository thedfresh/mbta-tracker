"""Live preview server for the MBTA LED matrix renderer."""

from __future__ import annotations

import argparse
import json
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from src.config import load_config
from src.data.collector_client import fetch_snapshot
from src.display import MatrixDisplay, MatrixGeometry
from src.data.poller import PollResult
from src.logic.scorer import estimate_time_to_linden, score_trip
from src.rendering import FrameData, TripRow, compose_frame, save_frame

FRAME_PATH = Path("emulator_output/frame.png")
SCHEDULE_SNAPSHOT_PATH = Path("logs/schedule_snapshots.jsonl")
DEBUG_TREND = True


def _parse_time(value: str) -> datetime | None:
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _minutes_away(now: datetime, dt: datetime) -> float:
    return (dt - now).total_seconds() / 60.0


def _format_clock(dt: datetime) -> str:
    value = dt.astimezone().strftime("%I:%M")
    return value.lstrip("0") if value.startswith("0") else value


def _load_boarding_schedule_map() -> dict[str, str]:
    if not SCHEDULE_SNAPSHOT_PATH.exists():
        return {}
    last_line = None
    try:
        with SCHEDULE_SNAPSHOT_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    last_line = line
    except Exception:
        return {}

    if not last_line:
        return {}

    try:
        entry = json.loads(last_line)
    except Exception:
        return {}

    schedules = entry.get("boarding", {}).get("schedules", []) or []
    schedule_map: dict[str, str] = {}
    for sched in schedules:
        trip_id = sched.get("trip_id")
        departure_time = sched.get("departure_time")
        if not trip_id:
            continue
        if departure_time:
            schedule_map[trip_id] = departure_time
    return schedule_map


def _build_frame_data(
    result: PollResult, drift_cache: dict[str, float]
) -> tuple[FrameData, list[str], dict[str, float]]:
    now = datetime.now(timezone.utc)
    trips: list[tuple[datetime, TripRow]] = []
    minutes_debug: list[str] = []
    seen_trip_ids: set[str] = set()

    schedule_map = _load_boarding_schedule_map()
    vehicles_by_id = {v.get("id"): v for v in result.vehicles if isinstance(v, dict)}
    next_cache: dict[str, float] = {}

    for pred in result.predictions:
        if not isinstance(pred, dict):
            continue
        attrs = pred.get("attributes", {})
        rels = pred.get("relationships", {})
        trip_rel = rels.get("trip") or {}
        trip_data = trip_rel.get("data") or {}
        trip_id = trip_data.get("id")
        if not trip_id:
            continue
        schedule_relationship = attrs.get("schedule_relationship")

        dep_raw = attrs.get("arrival_time") or attrs.get("departure_time")
        if not dep_raw:
            continue
        dep_time = _parse_time(dep_raw)
        if not dep_time:
            continue
        minutes = _minutes_away(now, dep_time)
        if minutes > 90:
            continue

        if trip_id:
            seen_trip_ids.add(trip_id)

        assessment = score_trip(pred, vehicles_by_id, minutes)

        if schedule_relationship == "CANCELLED":
            scheduled_time = schedule_map.get(trip_id) if trip_id else None
            if scheduled_time:
                scheduled_dt = _parse_time(scheduled_time)
                if scheduled_dt and scheduled_dt < now:
                    continue
                clock_time = _format_clock(scheduled_dt) if scheduled_dt else ""
                minutes = _minutes_away(now, scheduled_dt) if scheduled_dt else minutes
                sort_time = scheduled_dt or dep_time
            else:
                clock_time = ""
                sort_time = dep_time

            trips.append(
                (
                    sort_time,
                    TripRow(
                        minutes_away=minutes,
                        clock_time=clock_time,
                        reliability="UNKNOWN",
                        cancelled=True,
                        trend="stable",
                    ),
                )
            )
            continue

        minutes_debug.append(f"{minutes:.1f}")

        vehicle_rel = rels.get("vehicle") or {}
        vehicle_data = vehicle_rel.get("data") or {}
        vehicle_id = vehicle_data.get("id")
        departed = minutes <= 0.5
        trend = "stable"
        time_needed = None
        if vehicle_id:
            vehicle = vehicles_by_id.get(vehicle_id)
            if vehicle:
                attrs_v = vehicle.get("attributes", {})
                direction_id = attrs_v.get("direction_id")
                seq = attrs_v.get("current_stop_sequence")
                if direction_id == 1 and isinstance(seq, int) and 1 < seq <= 10:
                    departed = True
                time_needed = estimate_time_to_linden(vehicle)
                if time_needed is not None and trip_id:
                    if departed:
                        next_cache.pop(trip_id, None)
                        time_needed = 0.0
                        trend = "stable"
                    else:
                        prev = drift_cache.get(trip_id)
                        if prev is not None:
                            delta = prev - time_needed
                            if delta > 1:
                                trend = "improving"
                            elif delta < -1:
                                trend = "deteriorating"
                        next_cache[trip_id] = time_needed
                    if DEBUG_TREND:
                        print(
                            "trend_debug",
                            {
                                "trip_id": trip_id,
                                "time_needed": round(time_needed, 1),
                                "trend": trend,
                            },
                            flush=True,
                        )

        trips.append(
            (
                dep_time,
                TripRow(
                    minutes_away=minutes,
                    clock_time=_format_clock(dep_time),
                    reliability=assessment.classification,
                    departed=departed,
                    trend=trend,
                ),
            )
        )

    if len(trips) < 6 and schedule_map:
        for trip_id, dep_raw in schedule_map.items():
            if not trip_id:
                continue
            if trip_id in seen_trip_ids:
                continue
            dep_time = _parse_time(dep_raw)
            if not dep_time or dep_time < now:
                continue
            minutes = _minutes_away(now, dep_time)
            if minutes > 90:
                continue
            assessment = score_trip(
                {"relationships": {"trip": {"data": {"id": trip_id}}}}, {}, minutes
            )
            trips.append(
                (
                    dep_time,
                    TripRow(
                        minutes_away=minutes,
                        clock_time=_format_clock(dep_time),
                        reliability=assessment.classification,
                        scheduled_only=True,
                        trend="stable",
                    ),
                )
            )
            if len(trips) >= 6:
                break

    trips_sorted = sorted(trips, key=lambda t: t[0])[:6]
    data = FrameData(trips=[trip for _, trip in trips_sorted], ticker_text="")
    return data, minutes_debug, next_cache


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
      img { width: 768px; height: 256px; image-rendering: pixelated; }
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
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        choices=["emulator", "hardware", "both"],
        default="both",
        help="Frame output target",
    )
    parser.add_argument(
        "--no-server",
        action="store_true",
        help="Disable preview web server",
    )
    args = parser.parse_args()

    config = load_config()
    api_key = config.mbta.api_key

    output_emulator = args.output in {"emulator", "both"}
    output_hardware = args.output in {"hardware", "both"}

    if output_hardware:
        matrix = MatrixDisplay(
            MatrixGeometry(
                width=config.display.width,
                height=config.display.height,
                panel_height=config.display.height,
            ),
            brightness=config.display.brightness,
        )
        print("hardware_display_ready", {"panels": matrix.panel_count}, flush=True)
    else:
        matrix = None

    if not args.no_server:
        server_thread = threading.Thread(target=_run_server, daemon=True)
        server_thread.start()

    try:
        drift_cache: dict[str, float] = {}
        poll_interval_fast = 5
        poll_interval_slow = 10
        while True:
            timestamp = datetime.now(timezone.utc).isoformat()
            minutes_debug: list[str] = []
            reliability = "NONE"
            next_sleep = poll_interval_slow

            try:
                snapshot = fetch_snapshot(api_key)
                result = PollResult(
                    predictions=snapshot.boarding_predictions,
                    vehicles=snapshot.vehicles,
                    fetched_at=time.time(),
                    error=None,
                )
                frame_data, minutes_debug, drift_cache = _build_frame_data(result, drift_cache)
                reliability = frame_data.trips[0].reliability if frame_data.trips else "NONE"
                image = compose_frame(frame_data)
                if output_emulator:
                    save_frame(image, str(FRAME_PATH))
                if matrix is not None:
                    matrix.render(image)
                if any(trip.minutes_away <= 15 for trip in frame_data.trips):
                    next_sleep = poll_interval_fast
            except Exception as exc:
                print("preview_error", str(exc), flush=True)

            print(
                "preview_update",
                {
                    "timestamp": timestamp,
                    "minutes_away": minutes_debug,
                    "reliability": reliability,
                },
                flush=True,
            )

            time.sleep(next_sleep)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
