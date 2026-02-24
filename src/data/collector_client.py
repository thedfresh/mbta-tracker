"""Shared fetcher for Route 109 collection and live preview."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

MBTA_API_BASE = "https://api-v3.mbta.com"
ROUTE_ID = "109"
BOARDING_STOP_ID = "5483"
TERMINAL_STOP_ID = "7412"
DIRECTION_ID = 1

PREDICTION_FIELDS_BOARDING = "departure_time,arrival_time,stop_sequence,schedule_relationship"
PREDICTION_FIELDS_TERMINAL = "departure_time,schedule_relationship,stop_sequence"
VEHICLE_FIELDS = (
    "current_stop_sequence,current_status,direction_id,updated_at,latitude,longitude,bearing,speed"
)
SCHEDULE_FIELDS = "departure_time,stop_sequence"


@dataclass(frozen=True)
class CollectorSnapshot:
    boarding_predictions: list[dict[str, Any]]
    terminal_predictions: list[dict[str, Any]]
    vehicles: list[dict[str, Any]]


def _get(path: str, params: dict[str, Any], api_key: str) -> dict[str, Any]:
    url = f"{MBTA_API_BASE}{path}"
    resp = requests.get(url, params=params, headers={"x-api-key": api_key}, timeout=10)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
    return resp.json()


def fetch_boarding_predictions(api_key: str) -> list[dict[str, Any]]:
    params = {
        "filter[route]": ROUTE_ID,
        "filter[stop]": BOARDING_STOP_ID,
        "filter[direction_id]": DIRECTION_ID,
    }
    data = _get("/predictions", params=params, api_key=api_key)
    return data.get("data", []) or []


def fetch_terminal_predictions(api_key: str) -> list[dict[str, Any]]:
    params = {
        "filter[route]": ROUTE_ID,
        "filter[stop]": TERMINAL_STOP_ID,
        "filter[direction_id]": DIRECTION_ID,
        "fields[prediction]": PREDICTION_FIELDS_TERMINAL,
    }
    data = _get("/predictions", params=params, api_key=api_key)
    return data.get("data", []) or []


def fetch_vehicles(api_key: str) -> list[dict[str, Any]]:
    params = {
        "filter[route]": ROUTE_ID,
        "fields[vehicle]": VEHICLE_FIELDS,
    }
    data = _get("/vehicles", params=params, api_key=api_key)
    return data.get("data", []) or []


def fetch_schedules(api_key: str) -> list[dict[str, Any]]:
    params = {
        "filter[route]": ROUTE_ID,
        "filter[stop]": TERMINAL_STOP_ID,
        "filter[direction_id]": DIRECTION_ID,
        "fields[schedule]": SCHEDULE_FIELDS,
    }
    data = _get("/schedules", params=params, api_key=api_key)
    return data.get("data", []) or []


def fetch_boarding_schedules(api_key: str) -> list[dict[str, Any]]:
    params = {
        "filter[route]": ROUTE_ID,
        "filter[stop]": BOARDING_STOP_ID,
        "filter[direction_id]": DIRECTION_ID,
        "fields[schedule]": SCHEDULE_FIELDS,
    }
    data = _get("/schedules", params=params, api_key=api_key)
    return data.get("data", []) or []


def fetch_snapshot(api_key: str) -> CollectorSnapshot:
    return CollectorSnapshot(
        boarding_predictions=fetch_boarding_predictions(api_key),
        terminal_predictions=fetch_terminal_predictions(api_key),
        vehicles=fetch_vehicles(api_key),
    )
