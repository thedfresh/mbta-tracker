from __future__ import annotations

from typing import Any
from unittest.mock import Mock, patch

import pytest
import requests

from src.data.mbta_client import MBTAClient, MBTAClientError


@pytest.fixture()
def mbta_client() -> MBTAClient:
    return MBTAClient("test-key")


def _mock_response(status_code: int, json_data: dict[str, Any] | None = None, text: str = "") -> Mock:
    response = Mock()
    response.status_code = status_code
    response.text = text
    if json_data is not None:
        response.json.return_value = json_data
    else:
        response.json.side_effect = ValueError("Invalid JSON")
    return response


def test_get_predictions_returns_data_and_vehicles(mbta_client: MBTAClient) -> None:
    response = _mock_response(200, {"data": [{"id": "p1"}], "included": [{"id": "v1"}]})
    with patch("requests.get", return_value=response) as mock_get:
        predictions, vehicles = mbta_client.get_predictions("109", "stop1", 1)

    assert predictions == [{"id": "p1"}]
    assert vehicles == [{"id": "v1"}]
    mock_get.assert_called_once()


def test_get_predictions_empty_included(mbta_client: MBTAClient) -> None:
    response = _mock_response(200, {"data": [{"id": "p1"}]})
    with patch("requests.get", return_value=response) as mock_get:
        predictions, vehicles = mbta_client.get_predictions("109", "stop1", 1)

    assert predictions == [{"id": "p1"}]
    assert vehicles == []
    mock_get.assert_called_once()


def test_get_vehicles_returns_data(mbta_client: MBTAClient) -> None:
    response = _mock_response(200, {"data": [{"id": "v1"}]})
    with patch("requests.get", return_value=response) as mock_get:
        vehicles = mbta_client.get_vehicles("109")

    assert vehicles == [{"id": "v1"}]
    mock_get.assert_called_once()


def test_non_200_raises_mbta_client_error(mbta_client: MBTAClient) -> None:
    response = _mock_response(404, {"error": "Not found"}, text="Not found")
    with patch("requests.get", return_value=response):
        with pytest.raises(MBTAClientError) as exc_info:
            mbta_client.get_vehicles("109")

    assert "404" in str(exc_info.value)


def test_network_error_raises_mbta_client_error(mbta_client: MBTAClient) -> None:
    with patch("requests.get", side_effect=requests.exceptions.ConnectionError("boom")):
        with pytest.raises(MBTAClientError):
            mbta_client.get_vehicles("109")


def test_invalid_json_raises_mbta_client_error(mbta_client: MBTAClient) -> None:
    response = _mock_response(200, None)
    with patch("requests.get", return_value=response):
        with pytest.raises(MBTAClientError):
            mbta_client.get_vehicles("109")
