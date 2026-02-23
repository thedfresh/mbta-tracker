"""Reliability scoring for MBTA inbound predictions."""

from __future__ import annotations

from dataclasses import dataclass
import time

from src.data.poller import PollResult


GOOD = "GOOD"
RISKY = "RISKY"
BAD = "BAD"
UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ReliabilityAssessment:
    """Result of reliability scoring for the next inbound departure."""

    classification: str
    reason: str


def assess_reliability(prediction: dict, vehicles: list[dict]) -> ReliabilityAssessment:
    """Assess reliability for a single prediction using vehicle data."""
    now = time.time()

    attributes = prediction.get("attributes", {})
    if attributes.get("schedule_relationship") == "CANCELLED":
        return ReliabilityAssessment(UNKNOWN, "No active predictions")

    relationships = prediction.get("relationships", {})
    vehicle_rel = relationships.get("vehicle", {}).get("data")
    vehicle_id = vehicle_rel.get("id") if isinstance(vehicle_rel, dict) else None

    if not vehicle_id:
        return ReliabilityAssessment(RISKY, "Prediction has no assigned vehicle")

    vehicles_by_id = {v.get("id"): v for v in vehicles if isinstance(v, dict)}
    vehicle = vehicles_by_id.get(vehicle_id)
    if not vehicle:
        return ReliabilityAssessment(RISKY, "Assigned vehicle missing from include data")

    v_updated = vehicle.get("attributes", {}).get("updated_at")
    if not v_updated:
        return ReliabilityAssessment(RISKY, "Vehicle has no update timestamp")

    return ReliabilityAssessment(GOOD, "Vehicle assigned with recent data")


def assess_poll(result: PollResult) -> ReliabilityAssessment:
    """Assess reliability for the first non-cancelled prediction in a PollResult."""
    if not result.predictions:
        return ReliabilityAssessment(UNKNOWN, "No active predictions")

    if result.error:
        return ReliabilityAssessment(UNKNOWN, f"Fetch error: {result.error}")

    age_seconds = time.time() - result.fetched_at
    if age_seconds > 120:
        return ReliabilityAssessment(BAD, f"Data is stale ({int(age_seconds)}s old)")
    if age_seconds > 45:
        return ReliabilityAssessment(RISKY, f"Data is aging ({int(age_seconds)}s old)")

    for prediction in result.predictions:
        attributes = prediction.get("attributes", {})
        if attributes.get("schedule_relationship") != "CANCELLED":
            return assess_reliability(prediction, result.vehicles)

    return ReliabilityAssessment(UNKNOWN, "No active predictions")


__all__ = [
    "GOOD",
    "RISKY",
    "BAD",
    "UNKNOWN",
    "ReliabilityAssessment",
    "assess_reliability",
    "assess_poll",
]
