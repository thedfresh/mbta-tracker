from __future__ import annotations

import time

from src.data.poller import PollResult
from src.logic.scorer import BAD, GOOD, RISKY, UNKNOWN, assess_reliability


def _poll_result(
    *,
    predictions,
    vehicles,
    fetched_at: float | None = None,
    error: str | None = None,
) -> PollResult:
    return PollResult(
        predictions=predictions,
        vehicles=vehicles,
        fetched_at=fetched_at if fetched_at is not None else time.time(),
        error=error,
    )


def test_assess_no_predictions_unknown() -> None:
    result = _poll_result(predictions=[], vehicles=[])

    assessment = assess_reliability(result)

    assert assessment.classification == UNKNOWN
    assert "No predictions" in assessment.reason


def test_assess_error_unknown() -> None:
    result = _poll_result(predictions=[{"id": "p1"}], vehicles=[], error="timeout")

    assessment = assess_reliability(result)

    assert assessment.classification == UNKNOWN
    assert "Fetch error" in assessment.reason


def test_assess_stale_bad() -> None:
    result = _poll_result(
        predictions=[{"id": "p1"}],
        vehicles=[],
        fetched_at=time.time() - 300,
    )

    assessment = assess_reliability(result)

    assert assessment.classification == BAD
    assert "stale" in assessment.reason


def test_assess_missing_vehicle_risky() -> None:
    result = _poll_result(
        predictions=[{"relationships": {"vehicle": {"data": None}}}],
        vehicles=[],
    )

    assessment = assess_reliability(result)

    assert assessment.classification == RISKY
    assert "no assigned vehicle" in assessment.reason


def test_assess_assigned_vehicle_good() -> None:
    result = _poll_result(
        predictions=[{"relationships": {"vehicle": {"data": {"id": "v1"}}}}],
        vehicles=[{"id": "v1", "attributes": {"updated_at": "2024-01-01T00:00:00Z"}}],
    )

    assessment = assess_reliability(result)

    assert assessment.classification == GOOD
    assert "Vehicle assigned" in assessment.reason
