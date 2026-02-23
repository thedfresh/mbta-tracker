"""Print ordered stop lists for MBTA Route 109 in both directions."""

from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv

MBTA_API_BASE = "https://api-v3.mbta.com"
ROUTE_ID = "109"

TARGET_STOP_NAMES = [
    "Broadway @ Shute St",
    "Linden Sq",
]


def _require_api_key() -> str:
    load_dotenv()
    api_key = os.environ.get("MBTA_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("MBTA_API_KEY is missing. Set it in .env.")
    return api_key


def _get(path: str, params: dict[str, Any], api_key: str) -> dict[str, Any]:
    url = f"{MBTA_API_BASE}{path}"
    resp = requests.get(url, params=params, headers={"x-api-key": api_key}, timeout=15)
    if resp.status_code != 200:
        raise SystemExit(f"Request failed: {resp.status_code} {resp.text}")
    return resp.json()


def _fetch_route_patterns(api_key: str) -> list[dict[str, Any]]:
    params = {
        "filter[route]": ROUTE_ID,
        "page[limit]": 50,
        "sort": "sort_order",
        "fields[route_pattern]": "direction_id,name,sort_order,typicality",
    }
    data = _get("/route_patterns", params=params, api_key=api_key)
    patterns = []
    for rp in data.get("data", []):
        patterns.append(
            {
                "id": rp.get("id"),
                "direction_id": rp.get("attributes", {}).get("direction_id"),
                "name": rp.get("attributes", {}).get("name"),
                "typicality": rp.get("attributes", {}).get("typicality"),
                "sort_order": rp.get("attributes", {}).get("sort_order"),
                "stops": [],
            }
        )
    return patterns


def _fetch_stops_for_pattern(api_key: str, pattern_id: str) -> list[dict[str, Any]]:
    params = {
        "filter[route_pattern]": pattern_id,
        "fields[stop]": "name",
    }
    data = _get("/stops", params=params, api_key=api_key)
    stops = []
    for stop in data.get("data", []):
        stops.append(
            {
                "sequence": stop.get("attributes", {}).get("sequence"),
                "id": stop.get("id"),
                "name": stop.get("attributes", {}).get("name", ""),
            }
        )
    stops.sort(key=lambda s: (s.get("sequence") is None, s.get("sequence") or 0))
    return stops


def _fetch_stops_for_pattern_direct(api_key: str, pattern_id: str) -> list[dict[str, Any]]:
    data = _get(f"/route_patterns/{pattern_id}/stops", params={}, api_key=api_key)
    stops = []
    for stop in data.get("data", []):
        stops.append(
            {
                "sequence": stop.get("attributes", {}).get("sequence"),
                "id": stop.get("id"),
                "name": stop.get("attributes", {}).get("name", ""),
            }
        )
    stops.sort(key=lambda s: (s.get("sequence") is None, s.get("sequence") or 0))
    return stops


def _fetch_stops_for_direction(api_key: str, direction_id: int) -> list[dict[str, Any]]:
    params = {
        "filter[route]": ROUTE_ID,
        "filter[direction_id]": direction_id,
        "fields[stop]": "name",
    }
    data = _get("/stops", params=params, api_key=api_key)
    stops = []
    for stop in data.get("data", []):
        stops.append(
            {
                "sequence": stop.get("attributes", {}).get("sequence"),
                "id": stop.get("id"),
                "name": stop.get("attributes", {}).get("name", ""),
            }
        )
    stops.sort(key=lambda s: (s.get("sequence") is None, s.get("sequence") or 0))
    return stops


def _select_pattern(patterns: list[dict[str, Any]], direction_id: int) -> dict[str, Any] | None:
    candidates = [p for p in patterns if p.get("direction_id") == direction_id]
    if not candidates:
        return None
    candidates.sort(key=lambda p: (p.get("typicality") or 99, p.get("sort_order") or 99))
    return candidates[0]


def _find_stop_ids(stops: list[dict[str, Any]]) -> dict[str, list[str]]:
    matches: dict[str, list[str]] = {name: [] for name in TARGET_STOP_NAMES}
    for stop in stops:
        stop_name = (stop.get("name") or "").lower()
        for name in TARGET_STOP_NAMES:
            if name.lower() in stop_name:
                matches[name].append(stop.get("id"))
    return matches


def main() -> int:
    api_key = _require_api_key()
    patterns = _fetch_route_patterns(api_key)

    direction0 = _select_pattern(patterns, 0)
    direction1 = _select_pattern(patterns, 1)

    if not direction0 or not direction1:
        raise SystemExit("Could not find route patterns for both directions.")

    # Try to fetch ordered stops for each pattern; fall back to route+direction if needed.
    for direction_id, pattern in [(0, direction0), (1, direction1)]:
        try:
            stops = _fetch_stops_for_pattern_direct(api_key, pattern["id"])
        except SystemExit:
            stops = []
        if not stops:
            try:
                stops = _fetch_stops_for_pattern(api_key, pattern["id"])
            except SystemExit:
                stops = []
        if not stops:
            stops = _fetch_stops_for_direction(api_key, direction_id)
        pattern["stops"] = stops

    print(f"Route {ROUTE_ID} stop sequences (from route_patterns)")

    for label, pattern in [("Direction 0", direction0), ("Direction 1", direction1)]:
        print(f"\n{label}: {pattern.get('name')}")
        stops = pattern.get("stops", [])
        missing_sequences = any(stop.get("sequence") is None for stop in stops)
        for idx, stop in enumerate(stops, start=1):
            seq = stop.get("sequence")
            seq_label = f"{seq:>2}" if isinstance(seq, int) else f"{idx:>2}?"
            print(f"  {seq_label}. {stop['id']} — {stop['name']}")
        if missing_sequences:
            print("  Note: '?' indicates missing sequence from API; index order used instead.")

        matches = _find_stop_ids(stops)
        for name, ids in matches.items():
            if ids:
                print(f"  {name}: {', '.join(ids)}")
            else:
                print(f"  {name}: not found")

    print("\nDirection toward Harvard: direction_id 0 (inbound).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
