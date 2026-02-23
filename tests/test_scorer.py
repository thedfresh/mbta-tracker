from __future__ import annotations

import time

from src.data.poller import PollResult
from src.logic.scorer import BAD, GOOD, RISKY, UNKNOWN, assess_poll, assess_reliability


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


def _prediction(vehicle_id: str | None = None, schedule_relationship: str | None = None) -> dict:
    relationships = {"vehicle": {"data": {"id": vehicle_id}}} if vehicle_id else {"vehicle": {"data": None}}
    attributes = {}
    if schedule_relationship is not None:
        attributes["schedule_relationship"] = schedule_relationship
    return {"relationships": relationships, "attributes": attributes}


def test_assess_no_predictions_unknown() -> None:
    result = _poll_result(predictions=[], vehicles=[])

    assessment = assess_poll(result)

    assert assessment.classification == UNKNOWN
    assert "No active predictions" in assessment.reason


def test_assess_error_unknown() -> None:
    result = _poll_result(predictions=[_prediction()], vehicles=[], error="timeout")

    assessment = assess_poll(result)

    assert assessment.classification == UNKNOWN
    assert "Fetch error" in assessment.reason


def test_assess_stale_bad() -> None:
    result = _poll_result(
        predictions=[_prediction()],
        vehicles=[],
        fetched_at=time.time() - 300,
    )

    assessment = assess_poll(result)

    assert assessment.classification == BAD
    assert "stale" in assessment.reason


def test_assess_missing_vehicle_risky() -> None:
    prediction = _prediction(vehicle_id=None)
    assessment = assess_reliability(prediction, [])

    assert assessment.classification == RISKY
    assert "no assigned vehicle" in assessment.reason


def test_assess_assigned_vehicle_good() -> None:
    prediction = _prediction(vehicle_id="v1")
    assessment = assess_reliability(
        prediction,
        [{"id": "v1", "attributes": {"updated_at": "2024-01-01T00:00:00Z"}}],
    )

    assert assessment.classification == GOOD
    assert "Vehicle assigned" in assessment.reason


def test_assess_poll_skips_cancelled() -> None:
    result = _poll_result(
        predictions=[_prediction(vehicle_id=None, schedule_relationship="CANCELLED")],
        vehicles=[],
    )

    assessment = assess_poll(result)

    assert assessment.classification == UNKNOWN
    assert "No active predictions" in assessment.reason
