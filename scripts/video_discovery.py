"""Validate open-ended visual observations and build a sampled action flow."""

from __future__ import annotations

import math
from pydantic import BaseModel, ConfigDict, Field


class DetectedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1)
    evidence_seconds: list[float] = Field(min_length=1)
    uncertainty: str = ""


class Detection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=100)
    actions: list[DetectedAction] = Field(max_length=50)
    limitations: list[str] = Field(min_length=1)


def build_flow(detection: Detection, sampled_seconds: list[float], duration: float) -> dict:
    if not sampled_seconds or any(not math.isfinite(t) or not 0 <= t < duration for t in sampled_seconds):
        raise ValueError("Reviewed timestamps must be finite and inside the video.")
    actions = []
    for action in detection.actions:
        if not action.label.strip() or not action.reason.strip():
            raise ValueError("Action labels and reasons must not be blank.")
        times = sorted(set(action.evidence_seconds))
        if any(not math.isfinite(t) or not any(abs(t - sample) < 1e-6 for sample in sampled_seconds)
               for t in times):
            raise ValueError("Action evidence must reference a reviewed frame.")
        actions.append({**action.model_dump(), "evidence_seconds": times,
                        "first_seen_seconds": times[0], "last_seen_seconds": times[-1]})
    actions.sort(key=lambda action: action["first_seen_seconds"])
    for index, action in enumerate(actions, 1):
        action["id"] = index
    transitions = [{"from": left["id"], "to": right["id"],
                    "status": "sampled_before" if left["last_seen_seconds"] < right["first_seen_seconds"]
                    else "ambiguous",
                    "reason": "Order of supporting frames; not proof of continuous action boundaries."}
                   for left, right in zip(actions, actions[1:])]
    return {"title": detection.title, "actions": actions, "transitions": transitions,
            "sampled_seconds": sorted(set(sampled_seconds)), "limitations": detection.limitations,
            "time_note": "First/last seen are supporting sample times, not action start/end boundaries."}
