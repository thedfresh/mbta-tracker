"""Backtest feasibility-based reliability scoring using predictions and vehicle logs."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from statistics import mean
from typing import Any, Iterable, Iterator

PREDICTIONS_PATH = "data/samples/predictions.jsonl"
VEHICLES_PATH = "data/samples/vehicles.jsonl"

ROUTE_ID = "109"
STOP_BOARDING = "5483"
DIR_BOARDING = 1
SEQ_BOARDING = 10

INBOUND_END_SEQ = 44
OUTBOUND_END_SEQ = 41
INBOUND_DURATION_MIN = 66.0
OUTBOUND_DURATION_MIN = 54.0

BUFFER_GOOD_MIN = 10.0
BUFFER_RISKY_MIN = 20.0

ON_TIME_WINDOW_MIN = 2.0
ARRIVAL_MATCH_WINDOW_MIN = 120.0


@dataclass(frozen=True)
class PredictionSample:
    trip_id: str
    prediction_time: datetime
    predicted_departure: datetime
    classification: str
    available_min: float
    time_needed_min: float
    vehicle_id: str
    vehicle_direction: int | None
    vehicle_seq: int | None


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


def _vehicle_direction(vehicle: dict[str, Any]) -> int | None:
    return vehicle.get("attributes", {}).get("direction_id")


def _vehicle_map_from_included(included: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in included:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "vehicle":
            continue
        vid = item.get("id")
        if vid:
            result[vid] = item
    return result


def _time_needed_minutes(direction_id: int | None, seq: int | None) -> float | None:
    if direction_id is None or seq is None:
        return None
    if direction_id == 1:
        if seq <= 1:
            return 0.0
        remaining_inbound = max(INBOUND_END_SEQ - seq, 0) / INBOUND_END_SEQ * INBOUND_DURATION_MIN
        return remaining_inbound + OUTBOUND_DURATION_MIN
    if direction_id == 0:
        remaining_outbound = max(OUTBOUND_END_SEQ - seq, 0) / OUTBOUND_END_SEQ * OUTBOUND_DURATION_MIN
        return remaining_outbound
    return None


def _classify(time_needed: float, available: float) -> str:
    if time_needed <= available - BUFFER_GOOD_MIN:
        return "GOOD"
    if time_needed <= available + BUFFER_RISKY_MIN:
        return "RISKY"
    return "BAD"


def _summarize_errors(values: list[float]) -> str:
    if not values:
        return "n/a"
    return "mean {:.1f}, median {:.1f}, p75 {:.1f}".format(
        mean(values),
        sorted(values)[len(values) // 2],
        sorted(values)[int(0.75 * (len(values) - 1))],
    )


def main() -> int:
    pred_path = sys.argv[1] if len(sys.argv) > 1 else PREDICTIONS_PATH
    veh_path = sys.argv[2] if len(sys.argv) > 2 else VEHICLES_PATH

    samples_by_trip: dict[str, list[PredictionSample]] = defaultdict(list)
    arrivals_by_trip: dict[str, list[datetime]] = defaultdict(list)

    stats_outcomes = Counter()
    stats_class = Counter()
    stats_class_outcome = Counter()

    total_predictions = 0
    skipped_no_vehicle = 0
    skipped_past_departure = 0
    skipped_missing_trip = 0
    skipped_missing_time_needed = 0

    examples_correct_bad: list[str] = []
    examples_incorrect_bad: list[str] = []
    examples_incorrect_good: list[str] = []
    examples_false_negative: list[str] = []

    for pred_entry, veh_entry, ts in _iter_aligned(pred_path, veh_path):
        pred_data = pred_entry.get("data", {})
        predictions = pred_data.get("data", []) or []
        included = pred_data.get("included", []) or []
        vehicle_map = _vehicle_map_from_included(included)

        veh_data = veh_entry.get("data", {})
        vehicles = veh_data.get("data", []) or []

        # Record actual arrival time when vehicle reaches stop sequence 10 inbound.
        for vehicle in vehicles:
            if not isinstance(vehicle, dict):
                continue
            if _vehicle_route_id(vehicle) != ROUTE_ID:
                continue
            if _vehicle_direction(vehicle) != DIR_BOARDING:
                continue
            if _vehicle_seq(vehicle) != SEQ_BOARDING:
                continue
            trip_id = _vehicle_trip_id(vehicle)
            if trip_id:
                arrivals_by_trip[trip_id].append(ts)

        for pred in predictions:
            if not isinstance(pred, dict):
                continue
            if _prediction_route_id(pred) not in (None, ROUTE_ID):
                continue
            if _prediction_stop_id(pred) != STOP_BOARDING:
                continue
            if _prediction_direction(pred) != DIR_BOARDING:
                continue

            trip_id = _prediction_trip_id(pred)
            if not trip_id:
                skipped_missing_trip += 1
                continue

            dep_time = _prediction_departure_time(pred)
            if dep_time is None:
                continue

            minutes_until = (dep_time - ts).total_seconds() / 60.0
            if minutes_until <= 0:
                skipped_past_departure += 1
                continue

            vehicle_id = _prediction_vehicle_id(pred)
            if not vehicle_id:
                skipped_no_vehicle += 1
                continue

            vehicle = vehicle_map.get(vehicle_id)
            if not vehicle:
                skipped_no_vehicle += 1
                continue

            vehicle_direction = _vehicle_direction(vehicle)
            vehicle_seq = _vehicle_seq(vehicle)
            time_needed = _time_needed_minutes(vehicle_direction, vehicle_seq)
            if time_needed is None:
                skipped_missing_time_needed += 1
                continue

            classification = _classify(time_needed, minutes_until)
            total_predictions += 1

            samples_by_trip[trip_id].append(
                PredictionSample(
                    trip_id=trip_id,
                    prediction_time=ts,
                    predicted_departure=dep_time,
                    classification=classification,
                    available_min=minutes_until,
                    time_needed_min=time_needed,
                    vehicle_id=vehicle_id,
                    vehicle_direction=vehicle_direction,
                    vehicle_seq=vehicle_seq,
                )
            )

    # Evaluate outcomes
    tp = fp = fn = tn = 0
    deltas_by_class = defaultdict(list)

    for trip_id, samples in samples_by_trip.items():
        arrivals = sorted(arrivals_by_trip.get(trip_id, []))
        samples_sorted = sorted(samples, key=lambda s: s.prediction_time)
        arrival_idx = 0
        for sample in samples_sorted:
            arrival = None
            while arrival_idx < len(arrivals):
                candidate = arrivals[arrival_idx]
                if candidate >= sample.prediction_time:
                    minutes_from_prediction = (candidate - sample.prediction_time).total_seconds() / 60.0
                    if minutes_from_prediction <= ARRIVAL_MATCH_WINDOW_MIN:
                        arrival = candidate
                    break
                arrival_idx += 1

            if arrival is None:
                outcome = "miss"
                is_failure = True
                delta_min = None
            else:
                delta_min = (arrival - sample.predicted_departure).total_seconds() / 60.0
                if abs(delta_min) > 30:
                    outcome = "miss"
                    is_failure = True
                elif abs(delta_min) <= 5:
                    outcome = "on_time"
                    is_failure = False
                elif 5 < delta_min <= 15:
                    outcome = "late"
                    is_failure = True
                else:
                    outcome = "miss"
                    is_failure = True

            stats_outcomes[outcome] += 1

            stats_class[sample.classification] += 1
            stats_class_outcome[(sample.classification, outcome)] += 1

            if delta_min is not None and outcome in ("on_time", "late"):
                deltas_by_class[sample.classification].append(delta_min)

            predicted_bad = sample.classification == "BAD"
            if predicted_bad and is_failure:
                tp += 1
                if len(examples_correct_bad) < 3:
                    actual_text = arrival.isoformat() if arrival else "missing"
                    delta_text = f"{delta_min:.1f}" if delta_min is not None else "n/a"
                    examples_correct_bad.append(
                        f"{sample.trip_id} pred={sample.predicted_departure.isoformat()} actual={actual_text} delta={delta_text}"
                    )
            elif predicted_bad and not is_failure:
                fp += 1
                if len(examples_incorrect_bad) < 3:
                    examples_incorrect_bad.append(
                        f"{sample.trip_id} pred={sample.predicted_departure.isoformat()} actual={arrival.isoformat()} delta={delta_min:.1f}"
                    )
            elif (not predicted_bad) and is_failure:
                fn += 1
                if len(examples_incorrect_good) < 3:
                    actual = arrival.isoformat() if arrival else "missing"
                    delta_text = f"{delta_min:.1f}" if delta_min is not None else "n/a"
                    examples_incorrect_good.append(
                        f"{sample.trip_id} pred={sample.predicted_departure.isoformat()} actual={actual} delta={delta_text}"
                    )
                if len(examples_false_negative) < 5:
                    arrival_text = arrival.isoformat() if arrival else "missing"
                    delta_text = f"{delta_min:.1f}" if delta_min is not None else "n/a"
                    examples_false_negative.append(
                        "trip={trip} class={cls} avail={avail:.1f} need={need:.1f} "
                        "veh_dir={vdir} seq={seq} pred={pred} actual={actual} delta={delta}".format(
                            trip=sample.trip_id,
                            cls=sample.classification,
                            avail=sample.available_min,
                            need=sample.time_needed_min,
                            vdir=sample.vehicle_direction,
                            seq=sample.vehicle_seq,
                            pred=sample.predicted_departure.isoformat(),
                            actual=arrival_text,
                            delta=delta_text,
                        )
                    )
            else:
                tn += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0

    print("Feasibility backtest summary")
    print(f"Total predictions scored: {total_predictions}")
    print(f"Skipped (no vehicle): {skipped_no_vehicle}")
    print(f"Skipped (past departure): {skipped_past_departure}")
    print(f"Skipped (missing trip): {skipped_missing_trip}")
    print(f"Skipped (missing time needed): {skipped_missing_time_needed}")

    print("\nOutcome counts:")
    for key in ["on_time", "late", "miss"]:
        print(f"  {key}: {stats_outcomes[key]}")

    print("\nClassification counts:")
    for key in ["GOOD", "RISKY", "BAD"]:
        print(f"  {key}: {stats_class[key]}")

    print("\nClassification x outcome:")
    for cls in ["GOOD", "RISKY", "BAD"]:
        for outcome in ["on_time", "late", "miss"]:
            print(f"  {cls} / {outcome}: {stats_class_outcome[(cls, outcome)]}")

    print("\nError distributions (minutes, actual - predicted):")
    for cls in ["GOOD", "RISKY", "BAD"]:
        print(f"  {cls}: {_summarize_errors(deltas_by_class[cls])}")

    print("\nBAD precision/recall vs failures (late or miss):")
    print(f"  Precision: {precision:.3f}")
    print(f"  Recall: {recall:.3f}")

    if examples_correct_bad:
        print("\nExamples (BAD predicted, failure observed):")
        for ex in examples_correct_bad:
            print(f"  {ex}")

    if examples_incorrect_bad:
        print("\nExamples (BAD predicted, but on-time):")
        for ex in examples_incorrect_bad:
            print(f"  {ex}")

    if examples_incorrect_good:
        print("\nExamples (GOOD/RISKY predicted, but failure):")
        for ex in examples_incorrect_good:
            print(f"  {ex}")

    if examples_false_negative:
        print("\nFalse-negative details (for threshold tuning):")
        for ex in examples_false_negative:
            print(f"  {ex}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
