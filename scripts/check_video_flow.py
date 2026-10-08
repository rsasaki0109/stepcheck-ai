"""Compare independently specified flow order with recorded vision evidence times.

This checks the order of confirmations in sampled frames. It does not infer unseen
actions, continuous action intervals, or internal model attention.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_flow(flow: dict, review: dict, through_seconds: float | None = None) -> dict:
    expected = [step["index"] for step in flow["steps"]]
    if not expected or len(set(expected)) != len(expected):
        raise ValueError("Expected flow must contain unique step indices.")
    recorded = {step["index"]: step for step in review["steps"]}
    if len(recorded) != len(review["steps"]) or set(recorded) != set(expected):
        raise ValueError("Review must have exactly one result per expected flow step.")
    if through_seconds is not None and (not math.isfinite(through_seconds) or through_seconds < 0):
        raise ValueError("Playback time must be finite and non-negative.")
    states = []
    for item in flow["steps"]:
        step = recorded[item["index"]]
        evidence = step["evidence_seconds"]
        if not evidence or any(not math.isfinite(t) or not 0 <= t < review["duration_seconds"] for t in evidence):
            raise ValueError("Evidence times must be finite and inside the video.")
        confirmed_at = max(evidence)
        status = "observed" if step["status"] == "completed" else step["status"]
        if status not in {"observed", "unknown", "not_done"}:
            raise ValueError("Unsupported review status.")
        if through_seconds is not None and confirmed_at > through_seconds + 1e-6:
            status = "pending"
        states.append({"index": item["index"], "label": item["label"], "status": status,
                       "confirmed_seconds": confirmed_at if status == "observed" else None,
                       "reason": step["reason"]})
    observed = [state for state in states if state["status"] == "observed"]
    times = [state["confirmed_seconds"] for state in observed]
    # Compare in EXPECTED order; sorting the input by step index would hide inversions.
    inversions = [(a["index"], b["index"]) for i, a in enumerate(observed)
                  for b in observed[i + 1:] if a["confirmed_seconds"] > b["confirmed_seconds"]]
    if inversions:
        observed_status = "violated"
    elif len(observed) < 2:
        observed_status = "insufficient"
    elif len(set(times)) != len(times):
        observed_status = "ambiguous"
    else:
        observed_status = "consistent"
    edges = []
    for a, b in zip(states, states[1:]):
        if "pending" in (a["status"], b["status"]):
            status = "pending"
        elif a["status"] != "observed" or b["status"] != "observed":
            status = "unknown"
        elif a["confirmed_seconds"] > b["confirmed_seconds"]:
            status = "violated"
        elif a["confirmed_seconds"] == b["confirmed_seconds"]:
            status = "unknown"
        else:
            status = "consistent"
        edges.append({"from": a["index"], "to": b["index"], "status": status})
    if observed_status == "violated":
        overall = "violated"
    elif any(state["status"] == "pending" for state in states):
        overall = "pending"
    elif len(observed) == len(states) and observed_status == "consistent":
        overall = "verified"
    else:
        overall = "unknown"
    return {
        "title": flow["title"], "source_sha256": review["source_sha256"],
        "basis": "Order of recorded confirmation timestamps in sampled frames, not continuous action intervals",
        "overall_status": overall, "observed_order_status": observed_status,
        "observed_step_order": [state["index"] for state in sorted(observed, key=lambda state: state["confirmed_seconds"])],
        "unverified_steps": [state["index"] for state in states if state["status"] != "observed"],
        "inversions": [list(pair) for pair in inversions], "steps": states, "transitions": edges,
    }


def main():
    assets = ROOT / "docs" / "assets" / "video-demo"
    flow = json.loads((ROOT / "examples" / "handwashing-flow.json").read_text(encoding="utf-8"))
    review = json.loads((assets / "review.json").read_text(encoding="utf-8"))
    result = check_flow(flow, review)
    (assets / "order-review.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Observed order: {result['observed_order_status']}; full flow: {result['overall_status']}")


if __name__ == "__main__":
    main()
