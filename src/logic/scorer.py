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


def assess_reliability(result: PollResult) -> ReliabilityAssessment:
    """Assess reliability for the next inbound departure from a PollResult."""
    now = time.time()

    if not result.predictions:
        return ReliabilityAssessment(UNKNOWN, "No predictions available")

    if result.error:
        return ReliabilityAssessment(UNKNOWN, f"Fetch error: {result.error}")

    age_seconds = now - result.fetched_at
    if age_seconds > 120:
        return ReliabilityAssessment(BAD, f"Data is stale ({int(age_seconds)}s old)")
    if age_seconds > 45:
        return ReliabilityAssessment(RISKY, f"Data is aging ({int(age_seconds)}s old)")

    prediction = result.predictions[0]
    relationships = prediction.get("relationships", {})
    vehicle_rel = relationships.get("vehicle", {}).get("data")
    vehicle_id = vehicle_rel.get("id") if isinstance(vehicle_rel, dict) else None

    if not vehicle_id:
        return ReliabilityAssessment(RISKY, "Prediction has no assigned vehicle")

    vehicles_by_id = {v.get("id"): v for v in result.vehicles if isinstance(v, dict)}
    vehicle = vehicles_by_id.get(vehicle_id)
    if not vehicle:
        return ReliabilityAssessment(RISKY, "Assigned vehicle missing from include data")

    v_updated = vehicle.get("attributes", {}).get("updated_at")
    if not v_updated:
        return ReliabilityAssessment(RISKY, "Vehicle has no update timestamp")

    return ReliabilityAssessment(GOOD, "Vehicle assigned with recent data")


__all__ = [
    "GOOD",
    "RISKY",
    "BAD",
    "UNKNOWN",
    "ReliabilityAssessment",
    "assess_reliability",
]
