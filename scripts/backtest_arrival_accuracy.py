"""Backtest prediction accuracy at stop 5522 using aligned predictions and vehicles logs."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from statistics import mean, median
from typing import Any, Iterable, Iterator

PREDICTIONS_PATH = "data/samples/predictions.jsonl"
VEHICLES_PATH = "data/samples/vehicles.jsonl"

ROUTE_ID = "109"
STOP_BOARDING = "5522"
STOP_TERMINAL = "7412"
DIRECTION_INBOUND = 0

TIME_BUCKETS = [
    (">30", 30, float("inf")),
    ("15-30", 15, 30),
    ("<15", float("-inf"), 15),
]

POSITION_BUCKETS = [
    ("early", 0.0, 1 / 3),
    ("mid", 1 / 3, 2 / 3),
    ("late", 2 / 3, 1.1),
]


@dataclass(frozen=True)
class PredictionSample:
    predicted_departure: datetime
    time_bucket: str
    position_bucket: str


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


def _iter_aligned(pred_path: str, veh_path: str) -> Iterator[tuple[dict[str, Any], dict[str, Any], datetime]]:
    pred_iter = _iter_jsonl(pred_path)
    veh_iter = _iter_jsonl(veh_path)
    pred_entry = next(pred_iter, None)
    veh_entry = next(veh_iter, None)

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

        yield pred_entry, veh_entry, pred_ts
        pred_entry = next(pred_iter, None)
        veh_entry = next(veh_iter, None)


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


def _vehicle_status(vehicle: dict[str, Any]) -> str | None:
    return vehicle.get("attributes", {}).get("current_status")


def _vehicle_direction(vehicle: dict[str, Any]) -> int | None:
    return vehicle.get("attributes", {}).get("direction_id")


def _vehicle_map(vehicles: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for vehicle in vehicles:
        if not isinstance(vehicle, dict):
            continue
        if _vehicle_route_id(vehicle) != ROUTE_ID:
            continue
        vid = vehicle.get("id")
        if vid:
            result[vid] = vehicle
    return result


def _bucket_time(minutes: float) -> str:
    for label, low, high in TIME_BUCKETS:
        if low < minutes <= high:
            return label
    return ">30"


def _bucket_position(seq: int | None, max_seq: int | None) -> str:
    if seq is None or not max_seq:
        return "unknown"
    ratio = seq / max_seq
    for label, low, high in POSITION_BUCKETS:
        if low <= ratio < high:
            return label
    return "late"


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


def _summarize_bucket(name: str, values: list[float]) -> list[str]:
    if not values:
        return [f"{name}: 0 samples"]
    abs_values = [abs(v) for v in values]
    return [
        f"{name}: {len(values)} samples",
        "  mean {:.1f} min, median {:.1f}, p75 {:.1f}, p90 {:.1f}".format(
            mean(values),
            median(values),
            _percentile(values, 0.75),
            _percentile(values, 0.90),
        ),
        "  mean absolute error {:.1f} min".format(mean(abs_values)),
    ]


def _estimate_stop_5522_seq(pred_path: str, veh_path: str) -> tuple[int | None, dict[int, int]]:
    counts = Counter()
    max_seq_by_dir: dict[int, int] = {}

    for pred_entry, veh_entry, ts in _iter_aligned(pred_path, veh_path):
        veh_data = veh_entry.get("data", {})
        vehicles = veh_data.get("data", []) or []
        vehicle_map = _vehicle_map(vehicles)

        for vehicle in vehicles:
            if not isinstance(vehicle, dict):
                continue
            if _vehicle_route_id(vehicle) != ROUTE_ID:
                continue
            direction = _vehicle_direction(vehicle)
            seq = _vehicle_seq(vehicle)
            if direction is not None and seq is not None:
                max_seq_by_dir[direction] = max(max_seq_by_dir.get(direction, 0), seq)

        pred_data = pred_entry.get("data", {})
        predictions = pred_data.get("data", []) or []

        for pred in predictions:
            if not isinstance(pred, dict):
                continue
            if _prediction_direction(pred) != DIRECTION_INBOUND:
                continue
            if _prediction_stop_id(pred) != STOP_BOARDING:
                continue
            if _prediction_route_id(pred) not in (None, ROUTE_ID):
                continue

            vehicle_id = _prediction_vehicle_id(pred)
            if not vehicle_id:
                continue
            dep_time = _prediction_departure_time(pred)
            if dep_time is None:
                continue
            minutes = (dep_time - ts).total_seconds() / 60.0
            if abs(minutes) > 1:
                continue

            vehicle = vehicle_map.get(vehicle_id)
            if not vehicle:
                continue
            if _vehicle_direction(vehicle) != DIRECTION_INBOUND:
                continue
            if _vehicle_status(vehicle) != "STOPPED_AT":
                continue
            seq = _vehicle_seq(vehicle)
            if seq is not None:
                counts[seq] += 1

    if not counts:
        return None, max_seq_by_dir
    return counts.most_common(1)[0][0], max_seq_by_dir


def main() -> int:
    pred_path = sys.argv[1] if len(sys.argv) > 1 else PREDICTIONS_PATH
    veh_path = sys.argv[2] if len(sys.argv) > 2 else VEHICLES_PATH

    stop_seq, max_seq_by_dir = _estimate_stop_5522_seq(pred_path, veh_path)
    if stop_seq is None:
        print("Unable to infer stop sequence for stop 5522; no matches found.")
        return 1

    print(f"Inferred stop 5522 sequence (inbound): {stop_seq}")

    pending_predictions: dict[str, list[PredictionSample]] = defaultdict(list)
    arrival_times: dict[str, datetime] = {}

    deltas: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    total_predictions = 0
    matched_predictions = 0
    missing_vehicle = 0

    for pred_entry, veh_entry, ts in _iter_aligned(pred_path, veh_path):
        pred_data = pred_entry.get("data", {})
        predictions = pred_data.get("data", []) or []

        veh_data = veh_entry.get("data", {})
        vehicles = veh_data.get("data", []) or []
        vehicle_map = _vehicle_map(vehicles)

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

            dep_time = _prediction_departure_time(pred)
            if dep_time is None:
                continue

            vehicle_id = _prediction_vehicle_id(pred)
            if not vehicle_id:
                continue

            total_predictions += 1

            minutes = (dep_time - ts).total_seconds() / 60.0
            if minutes <= 0:
                continue
            time_bucket = _bucket_time(minutes)

            vehicle = vehicle_map.get(vehicle_id)
            if not vehicle:
                missing_vehicle += 1
                continue

            seq = _vehicle_seq(vehicle)
            direction = _vehicle_direction(vehicle)
            max_seq = max_seq_by_dir.get(direction) if direction is not None else None
            position_bucket = _bucket_position(seq, max_seq)

            pending_predictions[trip_id].append(
                PredictionSample(
                    predicted_departure=dep_time,
                    time_bucket=time_bucket,
                    position_bucket=position_bucket,
                )
            )

        for vehicle in vehicles:
            if not isinstance(vehicle, dict):
                continue
            if _vehicle_route_id(vehicle) != ROUTE_ID:
                continue
            if _vehicle_direction(vehicle) != DIRECTION_INBOUND:
                continue
            seq = _vehicle_seq(vehicle)
            if seq != stop_seq:
                continue
            trip_id = _vehicle_trip_id(vehicle)
            if not trip_id:
                continue
            if trip_id not in arrival_times:
                arrival_times[trip_id] = ts

        completed_trips = [trip_id for trip_id in pending_predictions if trip_id in arrival_times]
        for trip_id in completed_trips:
            arrival_time = arrival_times[trip_id]
            samples = pending_predictions.pop(trip_id, [])
            for sample in samples:
                delta_min = (arrival_time - sample.predicted_departure).total_seconds() / 60.0
                if abs(delta_min) > 30:
                    continue
                deltas[sample.position_bucket][sample.time_bucket].append(delta_min)
                matched_predictions += 1

    print("\nSummary")
    print("Total predictions with assigned vehicles:", total_predictions)
    print("Predictions missing vehicle snapshot:", missing_vehicle)
    print("Predictions matched to arrivals:", matched_predictions)

    print("\nAccuracy by vehicle position and prediction lead time:")
    for position in ["early", "mid", "late", "unknown"]:
        if position not in deltas:
            continue
        print(f"\nPosition: {position}")
        for time_bucket in [">30", "15-30", "<15"]:
            values = deltas[position].get(time_bucket, [])
            for line in _summarize_bucket(f"  Lead {time_bucket}", values):
                print(line)

    # Highlight most unreliable buckets by mean absolute error
    bucket_errors: list[tuple[float, str, str, int]] = []
    for position, time_map in deltas.items():
        for time_bucket, values in time_map.items():
            if not values:
                continue
            mae = mean(abs(v) for v in values)
            bucket_errors.append((mae, position, time_bucket, len(values)))

    bucket_errors.sort(reverse=True)
    print("\nMost unreliable buckets (by mean absolute error):")
    for mae, position, time_bucket, count in bucket_errors[:5]:
        print(f"  {position} / {time_bucket}: MAE {mae:.1f} min (n={count})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
