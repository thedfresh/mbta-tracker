"""Render a preview frame from a single poll log entry."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Any

from src.data.poller import PollResult
from src.logic.scorer import assess_reliability, UNKNOWN
from src.rendering import FrameData, TripRow, compose_frame, save_frame


def _parse_ts(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _format_clock(dt: datetime) -> str:
    clock = dt.astimezone().strftime("%I:%M")
    return clock.lstrip("0") if clock.startswith("0") else clock


def _minutes_until(departure_iso: str, now: datetime) -> int:
    dep = _parse_ts(departure_iso)
    minutes = (dep - now).total_seconds() / 60.0
    return max(int(round(minutes)), 0)


def _load_first_entry(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                return json.loads(line)
    raise ValueError(f"No entries found in {path}")


def _build_from_collector(entry: dict[str, Any]) -> tuple[list[TripRow], str]:
    timestamp = _parse_ts(entry["timestamp"])
    trips = []
    for pred in entry.get("boarding", {}).get("predictions", [])[:3]:
        dep = pred.get("departure_time")
        if not dep:
            continue
        trips.append(
            TripRow(
                minutes_away=_minutes_until(dep, timestamp),
                clock_time=_format_clock(_parse_ts(dep)),
                reliability=UNKNOWN,
            )
        )
    ticker = "Preview from collector log"
    return trips, ticker


def _build_from_raw(entry: dict[str, Any]) -> tuple[list[TripRow], str]:
    timestamp = _parse_ts(entry["timestamp"])
    data = entry.get("data", {})
    predictions = data.get("data", []) or []
    vehicles = [v for v in (data.get("included", []) or []) if v.get("type") == "vehicle"]

    poll = PollResult(predictions=predictions, vehicles=vehicles, fetched_at=timestamp.timestamp(), error=None)
    assessment = assess_reliability(poll)

    trips = []
    for idx, pred in enumerate(predictions[:3]):
        dep = pred.get("attributes", {}).get("departure_time")
        if not dep:
            continue
        reliability = assessment.classification if idx == 0 else UNKNOWN
        trips.append(
            TripRow(
                minutes_away=_minutes_until(dep, timestamp),
                clock_time=_format_clock(_parse_ts(dep)),
                reliability=reliability,
            )
        )
    ticker = "Preview from raw MBTA log"
    return trips, ticker


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="data/samples/predictions.jsonl")
    parser.add_argument("--output", default="emulator_output/frame.png")
    args = parser.parse_args()

    entry = _load_first_entry(args.path)
    if "boarding" in entry and "fleet" in entry:
        trips, ticker = _build_from_collector(entry)
    else:
        trips, ticker = _build_from_raw(entry)

    frame = compose_frame(FrameData(trips=trips, ticker_text=ticker))
    save_frame(frame, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
