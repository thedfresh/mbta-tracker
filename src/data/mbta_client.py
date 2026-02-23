"""MBTA v3 API client."""

from __future__ import annotations

from typing import Any

import requests

MBTA_API_BASE = "https://api-v3.mbta.com"


class MBTAClientError(Exception):
    """Raised when an MBTA API request fails or returns a non-200 response."""


class MBTAClient:
    """Thin wrapper around the MBTA v3 API using requests."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._timeout_seconds = 10

    def get_predictions(self, route_id: str, stop_id: str) -> tuple[list[dict], list[dict]]:
        """Fetch predictions for a route and stop; returns (predictions, vehicles)."""
        params = {
            "filter[route]": route_id,
            "filter[stop]": stop_id,
            "include": "vehicle",
        }
        response_json = self._get("/predictions", params=params)
        predictions = response_json.get("data", [])
        vehicles = response_json.get("included", [])
        return predictions, vehicles

    def get_vehicles(self, route_id: str) -> list[dict]:
        """Fetch vehicles for a route; returns the raw data array."""
        params = {"filter[route]": route_id}
        response_json = self._get("/vehicles", params=params)
        return response_json.get("data", [])

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{MBTA_API_BASE}{path}"
        headers = {"x-api-key": self._api_key}
        try:
            response = requests.get(url, headers=headers, params=params, timeout=self._timeout_seconds)
        except requests.RequestException as exc:
            raise MBTAClientError(f"MBTA API request failed: {exc}") from exc

        if response.status_code != 200:
            body_text = response.text.strip()
            detail = f"Status {response.status_code}"
            if body_text:
                detail = f"{detail}, Body: {body_text}"
            raise MBTAClientError(f"MBTA API request failed: {detail}")

        try:
            return response.json()
        except ValueError as exc:
            raise MBTAClientError("MBTA API response was not valid JSON") from exc
