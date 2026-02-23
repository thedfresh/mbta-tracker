from __future__ import annotations

import time
from unittest.mock import MagicMock

from src.data.mbta_client import MBTAClientError
from src.data.poller import MBTAPoller, PollResult


def test_get_latest_initially_none() -> None:
    client = MagicMock()
    poller = MBTAPoller(client=client, route_id="109", stop_id="stop1", poll_interval_seconds=1)

    assert poller.get_latest() is None


def test_fetch_once_success() -> None:
    client = MagicMock()
    client.get_predictions.return_value = ([{"id": "p1"}], [{"id": "v1"}])
    poller = MBTAPoller(client=client, route_id="109", stop_id="stop1", poll_interval_seconds=1)

    result = poller._fetch_once()

    assert result.predictions == [{"id": "p1"}]
    assert result.vehicles == [{"id": "v1"}]
    assert result.error is None
    assert isinstance(result.fetched_at, float)
    assert result.fetched_at > 0


def test_fetch_once_client_error() -> None:
    client = MagicMock()
    client.get_predictions.side_effect = MBTAClientError("timeout")
    poller = MBTAPoller(client=client, route_id="109", stop_id="stop1", poll_interval_seconds=1)

    result = poller._fetch_once()

    assert result.predictions == []
    assert result.vehicles == []
    assert result.error == "timeout"


def test_start_and_stop() -> None:
    client = MagicMock()
    client.get_predictions.return_value = ([], [])
    poller = MBTAPoller(client=client, route_id="109", stop_id="stop1", poll_interval_seconds=0.1)

    poller.start()

    deadline = time.time() + 2
    latest = None
    while time.time() < deadline:
        latest = poller.get_latest()
        if latest is not None:
            break
        time.sleep(0.1)

    assert isinstance(latest, PollResult)

    poller.stop()

    thread = poller._thread
    assert thread is not None

    deadline = time.time() + 2
    while time.time() < deadline and thread.is_alive():
        time.sleep(0.05)

    assert not thread.is_alive()
