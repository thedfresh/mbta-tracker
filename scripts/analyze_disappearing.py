"""Analyze disappearing predictions for stop 5522 in a JSONL poll log.

Each line is JSON: {"timestamp": "...", "data": {"data": [...], "included": [...]}}
The script streams the file and compares trips that disappear within 5 minutes
of departure against trips that complete normally.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

STOP_BOARDING = "5522"
DIRECTION_INBOUND = 0


@dataclass
class TripState:
    first_seen: datetime
    last_seen: datetime
    last_departure_time: datetime | None
    last_status: str | None
    last_vehicle_id: str | None
    ever_vehicle_assigned: bool
    last_vehicle_assigned_at: datetime | None
    unassigned_after_assigned: bool
    polls_seen: int


@dataclass
class GroupStats:
    count: int = 0
    assigned_ever: int = 0
    unassigned_after_assigned: int = 0
    polls_total: int = 0
    polls_min: int | None = None
    polls_max: int | None = None
    minutes_since_assignment_total: float = 0.0
    minutes_since_assignment_count: int = 0
    last_status_counts: Counter[str] = None

    def __post_init__(self) -> None:
        if self.last_status_counts is None:
            self.last_status_counts = Counter()

    def add_trip(self, state: TripState, disappear_ts: datetime) -> None:
        self.count += 1
        self.polls_total += state.polls_seen
        self.polls_min = state.polls_seen if self.polls_min is None else min(self.polls_min, state.polls_seen)
        self.polls_max = state.polls_seen if self.polls_max is None else max(self.polls_max, state.polls_seen)
        if state.ever_vehicle_assigned:
            self.assigned_ever += 1
            if state.last_vehicle_assigned_at is not None:
                minutes = (disappear_ts - state.last_vehicle_assigned_at).total_seconds() / 60.0
                self.minutes_since_assignment_total += minutes
                self.minutes_since_assignment_count += 1
        if state.unassigned_after_assigned:
            self.unassigned_after_assigned += 1
        if state.last_status:
            self.last_status_counts[state.last_status] += 1

    def render(self) -> list[str]:
        lines = []
        lines.append(f"Trips: {self.count}")
        if self.count:
            assigned_pct = 100.0 * self.assigned_ever / self.count
            unassigned_pct = 100.0 * self.unassigned_after_assigned / self.count
            lines.append(f"Ever assigned vehicle: {self.assigned_ever} ({assigned_pct:.1f}%)")
            lines.append(f"Unassigned after assigned: {self.unassigned_after_assigned} ({unassigned_pct:.1f}%)")

            avg_polls = self.polls_total / self.count
            lines.append(
                f"Polls seen per trip: avg {avg_polls:.1f}, min {self.polls_min}, max {self.polls_max}"
            )

            if self.minutes_since_assignment_count:
                avg_minutes = self.minutes_since_assignment_total / self.minutes_since_assignment_count
                lines.append(
                    f"Minutes from last assignment to disappearance: avg {avg_minutes:.1f}"
                )
            else:
                lines.append("Minutes from last assignment to disappearance: n/a")

            if self.last_status_counts:
                common = ", ".join(
                    f"{status}:{count}" for status, count in self.last_status_counts.most_common(5)
                )
                lines.append(f"Last status (top): {common}")
        return lines


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


def _prediction_departure_time(pred: dict[str, Any]) -> datetime | None:
    dep = pred.get("attributes", {}).get("departure_time")
    if not dep:
        return None
    return _parse_ts(dep)


def _prediction_status(pred: dict[str, Any]) -> str | None:
    return pred.get("attributes", {}).get("status")


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "data/samples/predictions.jsonl"

    active_trips: dict[str, TripState] = {}
    prev_trip_ids: set[str] = set()

    disappeared_stats = GroupStats()
    completed_stats = GroupStats()
    ignored_stats = GroupStats()

    for entry in _iter_lines(path):
        ts_raw = entry.get("timestamp")
        if not ts_raw:
            continue
        ts = _parse_ts(ts_raw)

        data = entry.get("data", {})
        predictions = data.get("data", []) or []

        current_trip_ids: set[str] = set()

        for pred in predictions:
            if not isinstance(pred, dict):
                continue
            if _prediction_direction(pred) != DIRECTION_INBOUND:
                continue
            if _prediction_stop_id(pred) != STOP_BOARDING:
                continue

            trip_id = _prediction_trip_id(pred)
            if not trip_id:
                continue
            current_trip_ids.add(trip_id)

            departure_time = _prediction_departure_time(pred)
            status = _prediction_status(pred)
            vehicle_id = _prediction_vehicle_id(pred)

            if trip_id not in active_trips:
                active_trips[trip_id] = TripState(
                    first_seen=ts,
                    last_seen=ts,
                    last_departure_time=departure_time,
                    last_status=status,
                    last_vehicle_id=vehicle_id,
                    ever_vehicle_assigned=vehicle_id is not None,
                    last_vehicle_assigned_at=ts if vehicle_id else None,
                    unassigned_after_assigned=False,
                    polls_seen=1,
                )
            else:
                state = active_trips[trip_id]
                if state.ever_vehicle_assigned and vehicle_id is None and state.last_vehicle_id is not None:
                    state.unassigned_after_assigned = True
                if vehicle_id and state.last_vehicle_id is None:
                    state.ever_vehicle_assigned = True
                    state.last_vehicle_assigned_at = ts
                if vehicle_id and state.last_vehicle_id != vehicle_id:
                    state.last_vehicle_assigned_at = ts
                state.last_seen = ts
                state.last_departure_time = departure_time
                state.last_status = status
                state.last_vehicle_id = vehicle_id
                state.polls_seen += 1

        disappeared = prev_trip_ids - current_trip_ids
        for trip_id in disappeared:
            state = active_trips.pop(trip_id, None)
            if not state:
                continue

            last_dep = state.last_departure_time
            if last_dep is None:
                ignored_stats.add_trip(state, ts)
                continue

            minutes_to_dep = (last_dep - ts).total_seconds() / 60.0
            if minutes_to_dep > 0 and minutes_to_dep <= 5:
                disappeared_stats.add_trip(state, ts)
            elif minutes_to_dep <= 0:
                completed_stats.add_trip(state, ts)
            else:
                ignored_stats.add_trip(state, ts)

        prev_trip_ids = current_trip_ids

    print("Disappearing vs completed summary for stop 5522")
    print("\nDisappeared within 5 minutes of departure:")
    for line in disappeared_stats.render():
        print("  " + line)

    print("\nCompleted (vanished after departure time):")
    for line in completed_stats.render():
        print("  " + line)

    print("\nOther/ignored disappearances (not within 5 minutes):")
    for line in ignored_stats.render():
        print("  " + line)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
