"""Route 109 inbound data collector."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv

MBTA_API_BASE = "https://api-v3.mbta.com"
ROUTE_ID = "109"
BOARDING_STOP_ID = "5483"
TERMINAL_STOP_ID = "7412"
DIRECTION_ID = 1

PREDICTION_FIELDS_BOARDING = "departure_time,arrival_time,stop_sequence,schedule_relationship"
PREDICTION_FIELDS_TERMINAL = "departure_time,schedule_relationship,stop_sequence"
VEHICLE_FIELDS = "current_stop_sequence,current_status,direction_id,updated_at"
SCHEDULE_FIELDS = "departure_time,stop_sequence"

POLL_INTERVAL_SECONDS_DEFAULT = 30
SCHEDULE_SNAPSHOT_INTERVAL_SECONDS = 3600

LOG_PATH = "logs/route109_inbound.jsonl"
SCHEDULE_LOG_PATH = "logs/schedule_snapshots.jsonl"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_config() -> dict[str, Any]:
    load_dotenv()
    api_key = os.environ.get("MBTA_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("MBTA_API_KEY missing in environment")
    poll_interval = int(os.environ.get("POLL_INTERVAL_SECONDS", POLL_INTERVAL_SECONDS_DEFAULT))
    return {"api_key": api_key, "poll_interval": poll_interval}


def _get(path: str, params: dict[str, Any], api_key: str) -> dict[str, Any]:
    url = f"{MBTA_API_BASE}{path}"
    resp = requests.get(url, params=params, headers={"x-api-key": api_key}, timeout=10)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
    return resp.json()


def _write_jsonl(path: str, record: dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


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


def _fetch_predictions(api_key: str, stop_id: str, fields: str) -> list[dict[str, Any]]:
    params = {
        "filter[route]": ROUTE_ID,
        "filter[stop]": stop_id,
        "filter[direction_id]": DIRECTION_ID,
        "fields[prediction]": fields,
    }
    data = _get("/predictions", params=params, api_key=api_key)
    return data.get("data", []) or []


def _fetch_vehicles(api_key: str) -> list[dict[str, Any]]:
    params = {
        "filter[route]": ROUTE_ID,
        "fields[vehicle]": VEHICLE_FIELDS,
    }
    data = _get("/vehicles", params=params, api_key=api_key)
    return data.get("data", []) or []


def _fetch_schedules(api_key: str) -> list[dict[str, Any]]:
    params = {
        "filter[route]": ROUTE_ID,
        "filter[stop]": TERMINAL_STOP_ID,
        "filter[direction_id]": DIRECTION_ID,
        "fields[schedule]": SCHEDULE_FIELDS,
    }
    data = _get("/schedules", params=params, api_key=api_key)
    return data.get("data", []) or []


def main() -> int:
    config = _load_config()
    api_key = config["api_key"]
    poll_interval = config["poll_interval"]

    print(
        "collector_config",
        json.dumps(
            {
                "route_id": ROUTE_ID,
                "direction_id": DIRECTION_ID,
                "boarding_stop_id": BOARDING_STOP_ID,
                "terminal_stop_id": TERMINAL_STOP_ID,
                "poll_interval_seconds": poll_interval,
            }
        ),
        flush=True,
    )

    last_schedule_snapshot = 0.0

    while True:
        timestamp = _utc_now_iso()
        error = None
        boarding_predictions: list[dict[str, Any]] = []
        terminal_predictions: list[dict[str, Any]] = []
        fleet: list[dict[str, Any]] = []

        try:
            boarding_raw = _fetch_predictions(api_key, BOARDING_STOP_ID, PREDICTION_FIELDS_BOARDING)
            terminal_raw = _fetch_predictions(api_key, TERMINAL_STOP_ID, PREDICTION_FIELDS_TERMINAL)
            vehicles_raw = _fetch_vehicles(api_key)

            boarding_predictions = [_prediction_record(p) for p in boarding_raw]
            terminal_predictions = [_terminal_prediction_record(p) for p in terminal_raw]
            fleet = [_vehicle_record(v) for v in vehicles_raw]
        except Exception as exc:
            error = str(exc)

        record = {
            "timestamp": timestamp,
            "boarding": {"predictions": boarding_predictions},
            "terminal": {"predictions": terminal_predictions},
            "fleet": fleet,
            "error": error,
        }
        _write_jsonl(LOG_PATH, record)

        now = time.time()
        if now - last_schedule_snapshot >= SCHEDULE_SNAPSHOT_INTERVAL_SECONDS:
            snapshot_error = None
            schedules: list[dict[str, Any]] = []
            try:
                schedules_raw = _fetch_schedules(api_key)
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
