"""Verify prediction log coverage for updated stop/direction filters."""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

STOP_NEW = "5483"  # Broadway @ Shute St, direction 1
DIR_NEW = 1

STOP_OLD = "5522"  # previous stop, direction 0
DIR_OLD = 0


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
    path = sys.argv[1] if len(sys.argv) > 1 else "data/samples/predictions.jsonl"

    total_polls = 0
    first_ts: datetime | None = None
    last_ts: datetime | None = None

    count_new = 0
    count_old = 0

    assignment_new = AssignmentStats()
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

    included_vehicle_hits = 0
    included_vehicle_missing = 0
    included_vehicle_total = 0

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

        data = entry.get("data", {})
        predictions = data.get("data", []) or []
        included = data.get("included", []) or []
        included_vehicle_ids = {
            item.get("id")
            for item in included
            if isinstance(item, dict) and item.get("type") == "vehicle"
        }

        for pred in predictions:
            if not isinstance(pred, dict):
                continue
            stop_id = _prediction_stop_id(pred)
            direction_id = _prediction_direction(pred)
            if stop_id == STOP_NEW and direction_id == DIR_NEW:
                count_new += 1
                vehicle_id = _prediction_vehicle_id(pred)
                if vehicle_id:
                    assignment_new.assigned += 1
                else:
                    assignment_new.unassigned += 1

                trip_id = _prediction_trip_id(pred)
                dep_iso = _prediction_departure_time(pred)
                if trip_id and dep_iso and vehicle_id:
                    minutes = _minutes_until(dep_iso, ts)
                    if (trip_id, dep_iso) not in first_assignment_seen:
                        first_assignment_seen.add((trip_id, dep_iso))
                        for label, low, high in assignment_bin_edges:
                            if low < minutes <= high:
                                assignment_bins[label] += 1
                                break

                if vehicle_id:
                    included_vehicle_total += 1
                    if vehicle_id in included_vehicle_ids:
                        included_vehicle_hits += 1
                    else:
                        included_vehicle_missing += 1

            if stop_id == STOP_OLD and direction_id == DIR_OLD:
                count_old += 1

    print("Prediction log coverage summary")
    print("File:", path)
    print("Total polls:", total_polls)
    if first_ts and last_ts:
        print("Date range:", first_ts.isoformat(), "to", last_ts.isoformat())

    print("\nPrediction counts by stop/direction:")
    print(f"  Stop {STOP_NEW} dir {DIR_NEW}: {count_new}")
    print(f"  Stop {STOP_OLD} dir {DIR_OLD}: {count_old}")

    print("\nStop 5483 (direction 1) vehicle assignment:")
    total_new = assignment_new.assigned + assignment_new.unassigned
    if total_new:
        assigned_pct = 100.0 * assignment_new.assigned / total_new
        unassigned_pct = 100.0 * assignment_new.unassigned / total_new
        print(f"  Assigned: {assignment_new.assigned} ({assigned_pct:.1f}%)")
        print(f"  Unassigned: {assignment_new.unassigned} ({unassigned_pct:.1f}%)")
    else:
        print("  No predictions for stop 5483")

    print("\nMinutes before departure when vehicle gets assigned (first observed):")
    for label, _, _ in assignment_bin_edges:
        print(f"  {label:>6}: {assignment_bins[label]}")

    print("\nIncluded vehicle data presence for stop 5483 predictions with vehicle_id:")
    if included_vehicle_total:
        hit_pct = 100.0 * included_vehicle_hits / included_vehicle_total
        miss_pct = 100.0 * included_vehicle_missing / included_vehicle_total
        print(f"  Included hits: {included_vehicle_hits} ({hit_pct:.1f}%)")
        print(f"  Included missing: {included_vehicle_missing} ({miss_pct:.1f}%)")
    else:
        print("  No vehicle-assigned predictions to check")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
