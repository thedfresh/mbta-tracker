"""Analyze trip durations and turnarounds from vehicle logs for Route 109."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from statistics import mean
from typing import Any, Iterable, Iterator

ROUTE_ID = "109"


@dataclass
class TripRecord:
    vehicle_id: str
    trip_id: str | None
    direction_id: int | None
    start_time: datetime
    end_time: datetime


@dataclass
class ActiveTrip:
    trip_id: str | None
    direction_id: int | None
    start_time: datetime
    last_time: datetime
    last_seq: int | None


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


def _vehicle_route_id(vehicle: dict[str, Any]) -> str | None:
    return (
        vehicle.get("relationships", {})
        .get("route", {})
        .get("data", {})
        .get("id")
    )


def _vehicle_trip_id(vehicle: dict[str, Any]) -> str | None:
    trip = vehicle.get("relationships", {}).get("trip", {}).get("data")
    if isinstance(trip, dict):
        return trip.get("id")
    return None


def _vehicle_seq(vehicle: dict[str, Any]) -> int | None:
    return vehicle.get("attributes", {}).get("current_stop_sequence")


def _vehicle_direction(vehicle: dict[str, Any]) -> int | None:
    return vehicle.get("attributes", {}).get("direction_id")


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    values_sorted = sorted(values)
    if len(values_sorted) == 1:
        return values_sorted[0]
    k = (len(values_sorted) - 1) * pct
    f = int(k)
    c = min(f + 1, len(values_sorted) - 1)
    if f == c:
        return values_sorted[f]
    d0 = values_sorted[f] * (c - k)
    d1 = values_sorted[c] * (k - f)
    return d0 + d1


def _minutes(delta_seconds: float) -> float:
    return delta_seconds / 60.0


def _summarize(name: str, durations: list[float]) -> list[str]:
    lines = [f"{name} trips: {len(durations)}"]
    if durations:
        lines.append(
            "  avg {:.1f} min, min {:.1f}, max {:.1f}, p25 {:.1f}, p75 {:.1f}".format(
                mean(durations),
                min(durations),
                max(durations),
                _percentile(durations, 0.25),
                _percentile(durations, 0.75),
            )
        )
    return lines


def _summarize_simple(name: str, durations: list[float]) -> list[str]:
    lines = [f"{name}: {len(durations)}"]
    if durations:
        lines.append(
            "  avg {:.1f} min, min {:.1f}, max {:.1f}".format(
                mean(durations),
                min(durations),
                max(durations),
            )
        )
    return lines


def _filter_max(durations: list[float], max_minutes: float) -> list[float]:
    return [d for d in durations if d <= max_minutes]


def _is_peak(ts: datetime) -> bool:
    local_ts = ts.astimezone()
    hour = local_ts.hour
    return 7 <= hour < 10 or 16 <= hour < 19


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "data/samples/vehicles.jsonl"

    active: dict[str, ActiveTrip] = {}
    completed: list[TripRecord] = []

    inbound_durations: list[float] = []
    outbound_durations: list[float] = []

    turnaround_inbound_end: list[float] = []
    turnaround_outbound_end: list[float] = []

    peak_inbound: list[float] = []
    offpeak_inbound: list[float] = []
    peak_outbound: list[float] = []
    offpeak_outbound: list[float] = []

    last_trip_by_vehicle: dict[str, TripRecord] = {}

    for entry in _iter_jsonl(path):
        ts_raw = entry.get("timestamp")
        if not ts_raw:
            continue
        ts = _parse_ts(ts_raw)

        data = entry.get("data", {})
        vehicles = data.get("data", []) or []

        for vehicle in vehicles:
            if not isinstance(vehicle, dict):
                continue
            if _vehicle_route_id(vehicle) != ROUTE_ID:
                continue

            vehicle_id = vehicle.get("id")
            if not vehicle_id:
                continue

            seq = _vehicle_seq(vehicle)
            direction_id = _vehicle_direction(vehicle)
            trip_id = _vehicle_trip_id(vehicle)

            if seq is None:
                continue

            state = active.get(vehicle_id)
            if state is None:
                if seq == 1:
                    active[vehicle_id] = ActiveTrip(
                        trip_id=trip_id,
                        direction_id=direction_id,
                        start_time=ts,
                        last_time=ts,
                        last_seq=seq,
                    )
                continue

            reset = seq < (state.last_seq or seq)
            trip_changed = trip_id is not None and state.trip_id is not None and trip_id != state.trip_id
            if reset or trip_changed:
                trip_record = TripRecord(
                    vehicle_id=vehicle_id,
                    trip_id=state.trip_id,
                    direction_id=state.direction_id,
                    start_time=state.start_time,
                    end_time=state.last_time,
                )
                completed.append(trip_record)

                duration_min = _minutes((trip_record.end_time - trip_record.start_time).total_seconds())
                if trip_record.direction_id == 0:
                    inbound_durations.append(duration_min)
                    (peak_inbound if _is_peak(trip_record.start_time) else offpeak_inbound).append(duration_min)
                elif trip_record.direction_id == 1:
                    outbound_durations.append(duration_min)
                    (peak_outbound if _is_peak(trip_record.start_time) else offpeak_outbound).append(duration_min)

                prev_trip = last_trip_by_vehicle.get(vehicle_id)
                if prev_trip is not None:
                    turnaround = _minutes((trip_record.start_time - prev_trip.end_time).total_seconds())
                    if prev_trip.direction_id == 0:
                        turnaround_inbound_end.append(turnaround)
                    elif prev_trip.direction_id == 1:
                        turnaround_outbound_end.append(turnaround)

                last_trip_by_vehicle[vehicle_id] = trip_record

                active[vehicle_id] = ActiveTrip(
                    trip_id=trip_id,
                    direction_id=direction_id,
                    start_time=ts,
                    last_time=ts,
                    last_seq=seq,
                )
            else:
                state.last_time = ts
                state.last_seq = seq
                if trip_id is not None:
                    state.trip_id = trip_id
                if direction_id is not None:
                    state.direction_id = direction_id

    print("Route 109 trip duration summary (from vehicles.jsonl)")
    print("\nInbound duration:")
    for line in _summarize("Inbound", inbound_durations):
        print(line)

    print("\nOutbound duration:")
    for line in _summarize("Outbound", outbound_durations):
        print(line)

    print("\nTurnaround times (end of trip to next start for same vehicle):")
    for line in _summarize_simple("Inbound end", turnaround_inbound_end):
        print(line)
    for line in _summarize_simple("Outbound end", turnaround_outbound_end):
        print(line)

    print("\nTurnaround times (filtered <= 90 min):")
    for line in _summarize_simple(
        "Inbound end (filtered)",
        _filter_max(turnaround_inbound_end, 90),
    ):
        print(line)
    for line in _summarize_simple(
        "Outbound end (filtered)",
        _filter_max(turnaround_outbound_end, 90),
    ):
        print(line)

    print("\nTime-of-day patterns (start time local):")
    print("Inbound peak:")
    for line in _summarize("Inbound peak", peak_inbound):
        print(line)
    print("Inbound off-peak:")
    for line in _summarize("Inbound off-peak", offpeak_inbound):
        print(line)
    print("Outbound peak:")
    for line in _summarize("Outbound peak", peak_outbound):
        print(line)
    print("Outbound off-peak:")
    for line in _summarize("Outbound off-peak", offpeak_outbound):
        print(line)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
