"""Analyze vehicle positions for stop 5522 predictions using aligned JSONL logs."""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Iterator

PREDICTIONS_PATH = "data/samples/predictions.jsonl"
VEHICLES_PATH = "data/samples/vehicles.jsonl"

ROUTE_ID = "109"
STOP_BOARDING = "5522"
STOP_TERMINAL = "7412"
DIRECTION_INBOUND = 0


@dataclass
class TripState:
    last_seen: datetime
    last_departure_time: datetime | None
    last_seq: int | None
    last_status: str | None
    polls_seen: int


@dataclass
class GroupStats:
    trips: int = 0
    seq_counts: Counter[int] = None
    status_counts: Counter[str] = None
    seq_total: int = 0
    seq_count: int = 0
    missing_seq: int = 0

    def __post_init__(self) -> None:
        if self.seq_counts is None:
            self.seq_counts = Counter()
        if self.status_counts is None:
            self.status_counts = Counter()

    def add_trip(self, state: TripState) -> None:
        self.trips += 1
        if state.last_seq is None:
            self.missing_seq += 1
        else:
            self.seq_counts[state.last_seq] += 1
            self.seq_total += state.last_seq
            self.seq_count += 1
        if state.last_status:
            self.status_counts[state.last_status] += 1

    def render(self, label: str) -> list[str]:
        lines = [f"{label} trips: {self.trips}"]
        if self.trips:
            if self.seq_count:
                avg_seq = self.seq_total / self.seq_count
                lines.append(f"Avg last current_stop_sequence: {avg_seq:.2f}")
            lines.append(f"Trips missing current_stop_sequence: {self.missing_seq}")
            if self.seq_counts:
                top_seq = ", ".join(
                    f"{seq}:{count}" for seq, count in self.seq_counts.most_common(5)
                )
                lines.append(f"Top last stop_sequence values: {top_seq}")
            if self.status_counts:
                top_status = ", ".join(
                    f"{status}:{count}" for status, count in self.status_counts.most_common(5)
                )
                lines.append(f"Top last status values: {top_status}")
        return lines


def _parse_ts(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _iter_jsonl(path: str) -> Iterator[dict[str, Any]]:
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


def _prediction_route_id(pred: dict[str, Any]) -> str | None:
    return (
        pred.get("relationships", {})
        .get("route", {})
        .get("data", {})
        .get("id")
    )


def _vehicle_direction(vehicle: dict[str, Any]) -> int | None:
    return vehicle.get("attributes", {}).get("direction_id")


def _vehicle_route_id(vehicle: dict[str, Any]) -> str | None:
    return (
        vehicle.get("relationships", {})
        .get("route", {})
        .get("data", {})
        .get("id")
    )


def _vehicle_seq(vehicle: dict[str, Any]) -> int | None:
    return vehicle.get("attributes", {}).get("current_stop_sequence")


def _vehicle_status(vehicle: dict[str, Any]) -> str | None:
    return vehicle.get("attributes", {}).get("current_status")


def _vehicle_map(vehicles: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for vehicle in vehicles:
        if not isinstance(vehicle, dict):
            continue
        if _vehicle_route_id(vehicle) != ROUTE_ID:
            continue
        if _vehicle_direction(vehicle) != DIRECTION_INBOUND:
            continue
        vid = vehicle.get("id")
        if vid:
            result[vid] = vehicle
    return result


def _distance_from_terminal(seq: int | None) -> int | None:
    if seq is None:
        return None
    # Assumes terminal is stop sequence 1. Distance is approximate in stops.
    return max(seq - 1, 0)


def main() -> int:
    predictions_path = sys.argv[1] if len(sys.argv) > 1 else PREDICTIONS_PATH
    vehicles_path = sys.argv[2] if len(sys.argv) > 2 else VEHICLES_PATH

    pred_iter = _iter_jsonl(predictions_path)
    veh_iter = _iter_jsonl(vehicles_path)

    pred_entry = next(pred_iter, None)
    veh_entry = next(veh_iter, None)

    total_joined = 0
    overall_seq = Counter()
    overall_status = Counter()
    overall_distance = Counter()
    missing_vehicle_matches = 0

    trips: dict[str, TripState] = {}
    prev_trip_ids: set[str] = set()

    disappeared = GroupStats()
    completed = GroupStats()
    unknown = GroupStats()

    while pred_entry is not None and veh_entry is not None:
        pred_ts_raw = pred_entry.get("timestamp")
        veh_ts_raw = veh_entry.get("timestamp")
        if not pred_ts_raw or not veh_ts_raw:
            pred_entry = next(pred_iter, None)
            veh_entry = next(veh_iter, None)
            continue

        pred_ts = _parse_ts(pred_ts_raw)
        veh_ts = _parse_ts(veh_ts_raw)

        if pred_ts < veh_ts:
            pred_entry = next(pred_iter, None)
            continue
        if veh_ts < pred_ts:
            veh_entry = next(veh_iter, None)
            continue

        pred_data = pred_entry.get("data", {})
        predictions = pred_data.get("data", []) or []

        veh_data = veh_entry.get("data", {})
        vehicles = veh_data.get("data", []) or []
        vehicle_map = _vehicle_map(vehicles)

        current_trip_ids: set[str] = set()

        for pred in predictions:
            if not isinstance(pred, dict):
                continue
            if _prediction_direction(pred) != DIRECTION_INBOUND:
                continue
            if _prediction_stop_id(pred) != STOP_BOARDING:
                continue
            if _prediction_route_id(pred) not in (None, ROUTE_ID):
                continue

            trip_id = _prediction_trip_id(pred)
            if not trip_id:
                continue
            current_trip_ids.add(trip_id)

            departure_time = _prediction_departure_time(pred)
            vehicle_id = _prediction_vehicle_id(pred)

            vehicle = vehicle_map.get(vehicle_id) if vehicle_id else None
            if vehicle_id and not vehicle:
                missing_vehicle_matches += 1

            seq = _vehicle_seq(vehicle) if vehicle else None
            status = _vehicle_status(vehicle) if vehicle else None
            distance = _distance_from_terminal(seq)

            if seq is not None:
                overall_seq[seq] += 1
            else:
                overall_seq["missing"] += 1
            if status:
                overall_status[status] += 1
            else:
                overall_status["missing"] += 1
            if distance is not None:
                overall_distance[distance] += 1
            total_joined += 1

            if trip_id not in trips:
                trips[trip_id] = TripState(
                    last_seen=pred_ts,
                    last_departure_time=departure_time,
                    last_seq=seq,
                    last_status=status,
                    polls_seen=1,
                )
            else:
                state = trips[trip_id]
                state.last_seen = pred_ts
                if departure_time is not None:
                    state.last_departure_time = departure_time
                if seq is not None:
                    state.last_seq = seq
                if status is not None:
                    state.last_status = status
                state.polls_seen += 1

        disappeared_ids = prev_trip_ids - current_trip_ids
        for trip_id in disappeared_ids:
            state = trips.pop(trip_id, None)
            if not state:
                continue
            if state.last_departure_time is None:
                unknown.add_trip(state)
                continue
            minutes_to_dep = (state.last_departure_time - pred_ts).total_seconds() / 60.0
            if minutes_to_dep > 0 and minutes_to_dep <= 5:
                disappeared.add_trip(state)
            elif minutes_to_dep <= 0:
                completed.add_trip(state)
            else:
                unknown.add_trip(state)

        prev_trip_ids = current_trip_ids
        pred_entry = next(pred_iter, None)
        veh_entry = next(veh_iter, None)

    print("Vehicle position summary for stop 5522 predictions (Route 109 inbound)")
    print("Total matched predictions:", total_joined)
    print("Missing vehicle matches:", missing_vehicle_matches)

    print("\nOverall current_stop_sequence distribution (top 10):")
    for seq, count in overall_seq.most_common(10):
        print(f"  {seq}: {count}")

    print("\nOverall current_status distribution (top 10):")
    for status, count in overall_status.most_common(10):
        print(f"  {status}: {count}")

    print("\nDistance from terminal (approx stops, top 10):")
    for dist, count in overall_distance.most_common(10):
        print(f"  {dist}: {count}")

    print("\nComparison by trip outcome:")
    for line in disappeared.render("Disappeared within 5 minutes"):
        print("  " + line)
    for line in completed.render("Completed normally"):
        print("  " + line)
    for line in unknown.render("Other/unknown"):
        print("  " + line)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
