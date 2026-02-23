"""Route 109 inbound data collector."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
import requests

from src.data.collector_client import (
    DIRECTION_ID,
    MBTA_API_BASE,
    ROUTE_ID,
    CollectorSnapshot,
    fetch_schedules,
    fetch_snapshot,
)

POLL_INTERVAL_SECONDS_DEFAULT = 30
SCHEDULE_SNAPSHOT_INTERVAL_SECONDS = 3600

LOG_PATH = "logs/route109_inbound.jsonl"
SCHEDULE_LOG_PATH = "logs/schedule_snapshots.jsonl"

TRANSFER_STOPS = {
    "sullivan": "29004",
    "union_sq": "2612",
    "harvard": "22549",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_config() -> dict[str, Any]:
    load_dotenv()
    api_key = os.environ.get("MBTA_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("MBTA_API_KEY missing in environment")
    poll_interval = int(os.environ.get("POLL_INTERVAL_SECONDS", POLL_INTERVAL_SECONDS_DEFAULT))
    return {"api_key": api_key, "poll_interval": poll_interval}


def _write_jsonl(path: str, record: dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _get(path: str, params: dict[str, Any], api_key: str) -> dict[str, Any]:
    url = f"{MBTA_API_BASE}{path}"
    resp = requests.get(url, params=params, headers={"x-api-key": api_key}, timeout=10)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
    return resp.json()


def _fetch_transfer_predictions(api_key: str, stop_id: str) -> list[dict[str, Any]]:
    params = {
        "filter[route]": ROUTE_ID,
        "filter[stop]": stop_id,
        "filter[direction_id]": DIRECTION_ID,
    }
    data = _get("/predictions", params=params, api_key=api_key)
    return data.get("data", []) or []


def _prediction_record(pred: dict[str, Any]) -> dict[str, Any]:
    attrs = pred.get("attributes", {})
    rels = pred.get("relationships", {})
    trip = rels.get("trip", {}).get("data")
    vehicle = rels.get("vehicle", {}).get("data")
    return {
        "trip_id": trip.get("id") if isinstance(trip, dict) else None,
        "departure_time": attrs.get("departure_time"),
        "arrival_time": attrs.get("arrival_time"),
        "stop_sequence": attrs.get("stop_sequence"),
        "schedule_relationship": attrs.get("schedule_relationship"),
        "vehicle_id": vehicle.get("id") if isinstance(vehicle, dict) else None,
    }


def _terminal_prediction_record(pred: dict[str, Any]) -> dict[str, Any]:
    attrs = pred.get("attributes", {})
    rels = pred.get("relationships", {})
    trip = rels.get("trip", {}).get("data")
    return {
        "trip_id": trip.get("id") if isinstance(trip, dict) else None,
        "departure_time": attrs.get("departure_time"),
        "schedule_relationship": attrs.get("schedule_relationship"),
        "stop_sequence": attrs.get("stop_sequence"),
    }


def _vehicle_record(vehicle: dict[str, Any]) -> dict[str, Any]:
    attrs = vehicle.get("attributes", {})
    rels = vehicle.get("relationships", {})
    trip = rels.get("trip", {}).get("data")
    return {
        "vehicle_id": vehicle.get("id"),
        "trip_id": trip.get("id") if isinstance(trip, dict) else None,
        "direction_id": attrs.get("direction_id"),
        "current_stop_sequence": attrs.get("current_stop_sequence"),
        "current_status": attrs.get("current_status"),
        "updated_at": attrs.get("updated_at"),
    }


def _schedule_record(schedule: dict[str, Any]) -> dict[str, Any]:
    attrs = schedule.get("attributes", {})
    return {
        "departure_time": attrs.get("departure_time"),
        "stop_sequence": attrs.get("stop_sequence"),
    }


def _log_snapshot(
    snapshot: CollectorSnapshot,
    timestamp: str,
    transfer_data: dict[str, dict[str, Any]],
) -> None:
    record = {
        "timestamp": timestamp,
        "boarding": {"predictions": [_prediction_record(p) for p in snapshot.boarding_predictions]},
        "terminal": {"predictions": [_terminal_prediction_record(p) for p in snapshot.terminal_predictions]},
        "transfers": transfer_data,
        "fleet": [_vehicle_record(v) for v in snapshot.vehicles],
        "error": None,
    }
    _write_jsonl(LOG_PATH, record)


def main() -> int:
    config = _load_config()
    api_key = config["api_key"]
    poll_interval = config["poll_interval"]

    print(
        "collector_config",
        json.dumps(
            {
                "poll_interval_seconds": poll_interval,
            }
        ),
        flush=True,
    )

    last_schedule_snapshot = 0.0

    while True:
        timestamp = _utc_now_iso()
        error = None

        transfer_data: dict[str, dict[str, Any]] = {}
        for key, stop_id in TRANSFER_STOPS.items():
            transfer_data[key] = {
                "stop_id": stop_id,
                "predictions": [],
                "error": None,
            }
            try:
                raw = _fetch_transfer_predictions(api_key, stop_id)
                transfer_data[key]["predictions"] = [_prediction_record(p) for p in raw]
            except Exception as exc:
                transfer_data[key]["error"] = str(exc)

        try:
            snapshot = fetch_snapshot(api_key)
            _log_snapshot(snapshot, timestamp, transfer_data)
        except Exception as exc:
            error = str(exc)
            record = {
                "timestamp": timestamp,
                "boarding": {"predictions": []},
                "terminal": {"predictions": []},
                "transfers": transfer_data,
                "fleet": [],
                "error": error,
            }
            _write_jsonl(LOG_PATH, record)

        now = time.time()
        if now - last_schedule_snapshot >= SCHEDULE_SNAPSHOT_INTERVAL_SECONDS:
            snapshot_error = None
            schedules: list[dict[str, Any]] = []
            try:
                schedules_raw = fetch_schedules(api_key)
                schedules = [_schedule_record(s) for s in schedules_raw]
            except Exception as exc:
                snapshot_error = str(exc)

            snapshot_record = {
                "timestamp": timestamp,
                "schedules": schedules,
                "error": snapshot_error,
            }
            _write_jsonl(SCHEDULE_LOG_PATH, snapshot_record)
            last_schedule_snapshot = now

        time.sleep(poll_interval)


if __name__ == "__main__":
    raise SystemExit(main())
