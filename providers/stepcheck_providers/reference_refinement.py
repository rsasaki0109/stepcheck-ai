"""Pure, bounded follow-up planning shared by MCP and Web verification."""

import math


POLICY = "At most one follow-up. Double interval to fit the complete requested image set; preserve unknowns and prior observed judgments."


class RefinementBudgetError(ValueError):
    """All requested source/context images cannot fit at this interval."""


class NoNewSamplesError(ValueError):
    """The selected interval supplies no images beyond the prior pass."""


def validate_options(interval, max_frames):
    if not math.isfinite(interval) or interval <= 0:
        raise ValueError("Refinement interval must be finite and positive.")
    if not 2 <= max_frames <= 96:
        raise ValueError("Refinement frame budget must be between 2 and 96.")


def plan_refinement(steps, reviewed_seconds, duration, interval, max_frames):
    validate_options(interval, max_frames)
    if not math.isfinite(duration) or duration <= 0 or not reviewed_seconds or any(
            not math.isfinite(t) or not 0 <= t < duration for t in reviewed_seconds):
        raise ValueError("Reviewed timestamps must be finite and inside the video.")
    for step in steps:
        if step["status"] not in ("observed", "unknown") or (
                step["status"] == "observed" and not step["evidence_seconds"]):
            raise ValueError("Invalid prior verdict.")
        if any(t not in reviewed_seconds for t in step["evidence_seconds"]):
            raise ValueError("Prior citation was not reviewed.")
    old_times = set(reviewed_seconds)
    windows, times = [], set()
    tail = round(max(0, duration - 0.1), 6)
    for index, step in enumerate(steps):
        if step["status"] != "unknown":
            continue
        before = next((s for s in reversed(steps[:index]) if s["status"] == "observed"), None)
        after = next((s for s in steps[index + 1:] if s["status"] == "observed"), None)
        start = max(before["evidence_seconds"]) if before else 0.0
        end = min(after["evidence_seconds"]) if after else tail
        if start >= end:
            start, end = 0.0, tail
        size = (end - start) / interval
        if not math.isfinite(size) or size > 10000:
            raise RefinementBudgetError("Refinement would exceed the frame budget; increase the interval.")
        count = math.ceil(size)
        candidates = {round(start + i * interval, 6) for i in range(count + 1)
                      if start + i * interval <= end}
        candidates -= old_times
        context = {start, end} | {t for t in step["evidence_seconds"] if start <= t <= end}
        times.update(candidates | context)
        windows.append({"step_id": step["step_id"], "start_seconds": start, "end_seconds": end})
    if not windows:
        raise ValueError("No unknown steps to refine.")
    if len(times) > max_frames:
        raise RefinementBudgetError("Refinement exceeds max_frames; increase the interval or frame budget.")
    if not times - old_times:
        raise NoNewSamplesError("No new samples at this interval; choose a finer interval.")
    return {"target_step_ids": [w["step_id"] for w in windows], "windows": windows,
        "sampled_seconds": sorted(times), "added_seconds": sorted(times - old_times),
        "selection_note": "Search windows use adjacent observed steps in the given reference as hints. They do not prove absence elsewhere or exclude out-of-order actions outside these windows."}


def fit_refinement_budget(steps, reviewed_seconds, duration, interval, max_frames):
    attempts = []
    for _ in range(16):
        try:
            plan = plan_refinement(steps, reviewed_seconds, duration, interval, max_frames)
        except RefinementBudgetError:
            attempts.append({"interval_seconds": interval, "status": "over_budget"})
            interval *= 2
        except NoNewSamplesError:
            attempts.append({"interval_seconds": interval, "status": "no_new_samples"})
            return {"plan": None, "chosen_interval_seconds": None, "attempts": attempts,
                "stop_reason": "no_new_samples"}
        else:
            attempts.append({"interval_seconds": interval, "status": "fits", "frames": len(plan["sampled_seconds"])})
            return {"plan": plan, "chosen_interval_seconds": interval, "attempts": attempts, "stop_reason": None}
    return {"plan": None, "chosen_interval_seconds": None, "attempts": attempts,
        "stop_reason": "refinement_budget_exhausted"}
