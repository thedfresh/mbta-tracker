"""Analyze MBTA Route 109 prediction logs in JSONL format.

Each line is a JSON object: {"timestamp": "...", "data": {"data": [...], "included": [...]}}
The script streams the file and prints summary stats.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


STOP_BOARDING = "5522"
STOP_TERMINAL = "7412"
DIRECTION_INBOUND = 0


@dataclass
class AssignmentStats:
    assigned: int = 0
    unassigned: int = 0


def _parse_ts(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _iter_lines(path: str) -> Iterable[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _prediction_stop_id(pred: dict[str, Any]) -> str | None:
    return (
        pred.get("relationships", {})
        .get("stop", {})
        .get("data", {})
        .get("id")
    )


def _prediction_vehicle_id(pred: dict[str, Any]) -> str | None:
    vehicle = (
        pred.get("relationships", {})
        .get("vehicle", {})
        .get("data")
    )
    if isinstance(vehicle, dict):
        return vehicle.get("id")
    return None


def _prediction_trip_id(pred: dict[str, Any]) -> str | None:
    trip = (
        pred.get("relationships", {})
        .get("trip", {})
        .get("data")
    )
    if isinstance(trip, dict):
        return trip.get("id")
    return None


def _prediction_direction(pred: dict[str, Any]) -> int | None:
    return pred.get("attributes", {}).get("direction_id")


def _prediction_departure_time(pred: dict[str, Any]) -> str | None:
    return pred.get("attributes", {}).get("departure_time")


def _minutes_until(dep_iso: str, now: datetime) -> float:
    dep_ts = _parse_ts(dep_iso)
    return (dep_ts - now).total_seconds() / 60.0


def main() -> int:
    if len(sys.argv) < 2:
        path = "data/samples/predictions.jsonl"
    else:
        path = sys.argv[1]

    total_polls = 0
    first_ts: datetime | None = None
    last_ts: datetime | None = None

    boarding_assignment = AssignmentStats()
    assignment_bins = Counter()
    assignment_bin_edges = [
        ("<=0", float("-inf"), 0),
        ("0-1", 0, 1),
        ("1-3", 1, 3),
        ("3-5", 3, 5),
        ("5-10", 5, 10),
        ("10-15", 10, 15),
        ("15-30", 15, 30),
        ("30-60", 30, 60),
        (">60", 60, float("inf")),
    ]

    polls_missing_boarding = 0
    polls_missing_terminal = 0

    prev_ts: datetime | None = None
    gap_counts = Counter()

    prev_close_departures: dict[str, datetime] = {}
    disappear_close_count = 0
    null_close_count = 0

    first_assignment_seen: set[tuple[str, str]] = set()

    for entry in _iter_lines(path):
        ts_raw = entry.get("timestamp")
        if not ts_raw:
            continue
        ts = _parse_ts(ts_raw)
        total_polls += 1

        if first_ts is None:
            first_ts = ts
        last_ts = ts

        if prev_ts is not None:
            gap = (ts - prev_ts).total_seconds()
            if gap > 10:
                gap_counts[">10s"] += 1
            if gap > 30:
                gap_counts[">30s"] += 1
            if gap > 60:
                gap_counts[">60s"] += 1
            if gap > 120:
                gap_counts[">120s"] += 1
            if gap > 300:
                gap_counts[">300s"] += 1
        prev_ts = ts

        data = entry.get("data", {})
        predictions = data.get("data", []) or []

        seen_boarding = False
        seen_terminal = False
        current_boarding_trips: set[str] = set()
        current_close_departures: dict[str, datetime] = {}

        for pred in predictions:
            if not isinstance(pred, dict):
                continue
            if _prediction_direction(pred) != DIRECTION_INBOUND:
                continue
            stop_id = _prediction_stop_id(pred)
            if stop_id == STOP_BOARDING:
                seen_boarding = True
            if stop_id == STOP_TERMINAL:
                seen_terminal = True

            if stop_id != STOP_BOARDING:
                continue

            vehicle_id = _prediction_vehicle_id(pred)
            if vehicle_id:
                boarding_assignment.assigned += 1
            else:
                boarding_assignment.unassigned += 1

            trip_id = _prediction_trip_id(pred)
            dep_iso = _prediction_departure_time(pred)
            if trip_id:
                current_boarding_trips.add(trip_id)

            if trip_id and dep_iso:
                minutes = _minutes_until(dep_iso, ts)
                if (trip_id, dep_iso) not in first_assignment_seen and vehicle_id:
                    first_assignment_seen.add((trip_id, dep_iso))
                    for label, low, high in assignment_bin_edges:
                        if low < minutes <= high:
                            assignment_bins[label] += 1
                            break

                if minutes <= 5:
                    current_close_departures[trip_id] = ts
            elif trip_id and dep_iso is None:
                if trip_id in prev_close_departures:
                    null_close_count += 1

        if not seen_boarding:
            polls_missing_boarding += 1
        if not seen_terminal:
            polls_missing_terminal += 1

        for trip_id in prev_close_departures:
            if trip_id not in current_boarding_trips:
                disappear_close_count += 1

        prev_close_departures = current_close_departures

    print("Summary for", path)
    print("Total polls:", total_polls)
    if first_ts and last_ts:
        print("Date range:", first_ts.isoformat(), "to", last_ts.isoformat())

    total_boarding = boarding_assignment.assigned + boarding_assignment.unassigned
    print("\nStop 5522 (boarding) vehicle assignment:")
    if total_boarding:
        assigned_pct = 100.0 * boarding_assignment.assigned / total_boarding
        unassigned_pct = 100.0 * boarding_assignment.unassigned / total_boarding
        print(f"Assigned: {boarding_assignment.assigned} ({assigned_pct:.1f}%)")
        print(f"Unassigned: {boarding_assignment.unassigned} ({unassigned_pct:.1f}%)")
    else:
        print("No predictions for stop 5522")

    print("\nMinutes before departure when vehicle gets assigned (first observed):")
    for label, _, _ in assignment_bin_edges:
        print(f"  {label:>6}: {assignment_bins[label]}")

    print("\nPredictions disappearing or departure_time going null close to departure (<=5 min):")
    print("Disappear count:", disappear_close_count)
    print("Departure time null count:", null_close_count)

    print("\nMissing data indicators:")
    if total_polls:
        print(f"Polls missing stop 5522 predictions: {polls_missing_boarding} ({(polls_missing_boarding/total_polls)*100:.1f}%)")
        print(f"Polls missing stop 7412 predictions: {polls_missing_terminal} ({(polls_missing_terminal/total_polls)*100:.1f}%)")

    print("\nPoll interval gaps (counts of gaps exceeding thresholds):")
    for label in [">10s", ">30s", ">60s", ">120s", ">300s"]:
        print(f"  {label:>5}: {gap_counts[label]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
