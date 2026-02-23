"""Reliability scoring for MBTA inbound predictions."""

from __future__ import annotations

from dataclasses import dataclass
import time

from src.data.poller import PollResult

INBOUND_END_SEQ = 44
OUTBOUND_END_SEQ = 41
INBOUND_DURATION_MIN = 66.0
OUTBOUND_DURATION_MIN = 54.0

FEASIBILITY_GOOD_BUFFER_MIN = 10.0
FEASIBILITY_RISKY_BUFFER_MIN = 20.0


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


def score_trip(
    prediction: dict | None,
    vehicles: dict[str, dict],
    minutes_until: int,
) -> ReliabilityAssessment:
    """Score a trip based on prediction/vehicle state and minutes until departure."""
    if prediction is None:
        if minutes_until > 20:
            return ReliabilityAssessment(UNKNOWN, "Scheduled")
        if 10 <= minutes_until <= 20:
            return ReliabilityAssessment(RISKY, "Scheduled soon")
        return ReliabilityAssessment(BAD, "Scheduled imminent")

    attributes = prediction.get("attributes", {})
    if attributes.get("schedule_relationship") == "CANCELLED":
        return ReliabilityAssessment(UNKNOWN, "Cancelled")

    relationships = prediction.get("relationships", {})
    vehicle_rel = relationships.get("vehicle", {}).get("data")
    vehicle_id = vehicle_rel.get("id") if isinstance(vehicle_rel, dict) else None

    if not vehicle_id:
        if minutes_until > 20:
            return ReliabilityAssessment(UNKNOWN, "Unassigned")
        if 10 <= minutes_until <= 20:
            return ReliabilityAssessment(RISKY, "Unassigned soon")
        return ReliabilityAssessment(BAD, "Unassigned imminent")

    vehicle = vehicles.get(vehicle_id)
    if not vehicle:
        return ReliabilityAssessment(RISKY, "Assigned vehicle missing")

    time_needed = estimate_time_to_linden(vehicle)
    if time_needed is None:
        return ReliabilityAssessment(RISKY, "Vehicle missing position")

    return score_feasibility(time_needed, minutes_until)


def estimate_time_to_linden(vehicle: dict) -> float | None:
    """Estimate minutes needed for a vehicle to reach Linden Sq."""
    attrs = vehicle.get("attributes", {}) if isinstance(vehicle, dict) else {}
    direction_id = attrs.get("direction_id")
    seq = attrs.get("current_stop_sequence")
    if direction_id is None or seq is None or not isinstance(seq, int):
        return None

    if direction_id == 1:
        if seq <= 1:
            return 0.0
        remaining_inbound = max(INBOUND_END_SEQ - seq, 0) / INBOUND_END_SEQ * INBOUND_DURATION_MIN
        return remaining_inbound + OUTBOUND_DURATION_MIN

    if direction_id == 0:
        remaining_outbound = max(OUTBOUND_END_SEQ - seq, 0) / OUTBOUND_END_SEQ * OUTBOUND_DURATION_MIN
        return remaining_outbound

    return None


def score_feasibility(time_needed: float, time_available: int) -> ReliabilityAssessment:
    """Score feasibility using time needed vs time available."""
    if time_needed <= time_available - FEASIBILITY_GOOD_BUFFER_MIN:
        return ReliabilityAssessment(GOOD, "Feasible")
    if time_needed <= time_available + FEASIBILITY_RISKY_BUFFER_MIN:
        return ReliabilityAssessment(RISKY, "Tight timing")
    return ReliabilityAssessment(BAD, "Unlikely to make it")


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
    "score_trip",
    "estimate_time_to_linden",
    "score_feasibility",
]
