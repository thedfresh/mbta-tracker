"""Threaded poller that periodically refreshes MBTA API data."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time

from src.data.mbta_client import MBTAClient, MBTAClientError


@dataclass(frozen=True)
class PollResult:
    """Snapshot of the latest MBTA API poll attempt."""

    predictions: list[dict]
    vehicles: list[dict]
    fetched_at: float
    error: str | None


class MBTAPoller:
    """Background poller that refreshes MBTA API data on a schedule."""

    def __init__(
        self,
        client: MBTAClient,
        route_id: str,
        stop_id: str,
        direction_id: int,
        poll_interval_seconds: int,
    ) -> None:
        self._client = client
        self._route_id = route_id
        self._stop_id = stop_id
        self._direction_id = direction_id
        self._poll_interval_seconds = poll_interval_seconds
        self._latest: PollResult | None = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def get_latest(self) -> PollResult | None:
        """Return the most recent poll result, if any."""
        with self._lock:
            return self._latest

    def start(self) -> None:
        """Start the background polling thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the polling thread to stop."""
        self._stop_event.set()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            result = self._fetch_once()
            with self._lock:
                self._latest = result
            self._stop_event.wait(timeout=self._poll_interval_seconds)

    def _fetch_once(self) -> PollResult:
        try:
            predictions, vehicles = self._client.get_predictions(
                self._route_id, self._stop_id, self._direction_id
            )
            return PollResult(
                predictions=predictions,
                vehicles=vehicles,
                fetched_at=time.time(),
                error=None,
            )
        except MBTAClientError as exc:
            return PollResult(
                predictions=[],
                vehicles=[],
                fetched_at=time.time(),
                error=str(exc),
            )


__all__ = ["PollResult", "MBTAPoller"]
