"""Pure, bounded follow-up planning shared by MCP and Web verification."""

import math


POLICY = "At most one follow-up. Preserve required context; bisect the largest unreviewed time gaps within the search windows until the requested spacing or image budget is reached. Preserve unknowns and prior observed judgments."


class RefinementBudgetError(ValueError):
    """All requested source/context images cannot fit at this interval."""


class NoNewSamplesError(ValueError):
    """The selected interval supplies no images beyond the prior pass."""


def validate_options(interval, max_frames):
    if not math.isfinite(interval) or interval <= 0:
        raise ValueError("Refinement interval must be finite and positive.")
    if not 2 <= max_frames <= 96:
        raise ValueError("Refinement frame budget must be between 2 and 96.")


def refinement_scope(steps, reviewed_seconds, duration):
    if not math.isfinite(duration) or duration <= 0 or not reviewed_seconds or any(
            not math.isfinite(t) or not 0 <= t < duration for t in reviewed_seconds):
        raise ValueError("Reviewed timestamps must be finite and inside the video.")
    for step in steps:
        if step["status"] not in ("observed", "unknown") or (
                step["status"] == "observed" and not step["evidence_seconds"]):
            raise ValueError("Invalid prior verdict.")
        if any(t not in reviewed_seconds for t in step["evidence_seconds"]):
            raise ValueError("Prior citation was not reviewed.")
    windows, context = [], set()
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
        context.update({start, end} | {t for t in step["evidence_seconds"] if start <= t <= end})
        windows.append({"step_id": step["step_id"], "start_seconds": start, "end_seconds": end})
    if not windows:
        raise ValueError("No unknown steps to refine.")
    return windows, context


def plan_refinement(steps, reviewed_seconds, duration, interval, max_frames):
    """Explicit uniform sampling, retained for manual MCP requests and old-run comparison."""
    validate_options(interval, max_frames)
    windows, times = refinement_scope(steps, reviewed_seconds, duration)
    old_times = set(reviewed_seconds)
    for window in windows:
        start, end = window["start_seconds"], window["end_seconds"]
        size = (end - start) / interval
        if not math.isfinite(size) or size > 10000:
            raise RefinementBudgetError("Refinement would exceed the frame budget; increase the interval.")
        count = math.ceil(size)
        times.update({round(start + i * interval, 6) for i in range(count + 1)
                      if start + i * interval <= end} - old_times)
    if len(times) > max_frames:
        raise RefinementBudgetError("Refinement exceeds max_frames; increase the interval or frame budget.")
    if not times - old_times:
        raise NoNewSamplesError("No new samples at this interval; choose a finer interval.")
    return {"target_step_ids": [w["step_id"] for w in windows], "windows": windows,
        "sampled_seconds": sorted(times), "added_seconds": sorted(times - old_times),
        "selection_note": "Search windows use adjacent observed steps in the given reference as hints. They do not prove absence elsewhere or exclude out-of-order actions outside these windows."}


def scoped_gaps(windows, times):
    gaps = set()
    for window in windows:
        start, end = window["start_seconds"], window["end_seconds"]
        points = sorted({start, end} | {t for t in times if start <= t <= end})
        gaps.update(zip(points, points[1:]))
    return sorted(gaps, key=lambda pair: (-round(pair[1] - pair[0], 6), pair[0], pair[1]))


def midpoint(start, end):
    return round(start + (end - start) / 2, 6)


def gap_selection(steps, reviewed_seconds, duration, interval, max_frames):
    validate_options(interval, max_frames)
    windows, context = refinement_scope(steps, reviewed_seconds, duration)
    selection = {"plan": None, "chosen_interval_seconds": None, "strategy": "gap_bisection", "attempts": []}
    if len(context) > max_frames:
        return {**selection, "stop_reason": "refinement_budget_exhausted"}
    old_times, times = set(reviewed_seconds), set(context)
    gaps = scoped_gaps(windows, old_times | times)
    before = max((b - a for a, b in gaps), default=0)
    while len(times) < max_frames:
        gaps = scoped_gaps(windows, old_times | times)
        eligible = [(a, b) for a, b in gaps if round(b - a, 6) > interval
                    and a < midpoint(a, b) < b]
        if not eligible:
            break
        start, end = eligible[0]
        times.add(midpoint(start, end))
    if not times - old_times:
        return {**selection, "stop_reason": "no_new_samples"}
    gaps = scoped_gaps(windows, old_times | times)
    after = max((b - a for a, b in gaps), default=0)
    plan = {"target_step_ids": [w["step_id"] for w in windows], "windows": windows,
        "sampled_seconds": sorted(times), "added_seconds": sorted(times - old_times),
        "sampling_strategy": "gap_bisection",
        "coverage": {"before_max_gap_seconds": round(before, 6), "after_max_gap_seconds": round(after, 6),
                     "requested_max_gap_seconds": interval, "budget_limited": round(after, 6) > interval},
        "selection_note": "Search windows use adjacent observed steps as hints. Required context is retained; new images bisect the largest gaps between all previously reviewed timestamps within these windows. Temporal spacing is not action evidence, spatial attention, or proof of absence or order outside the windows."}
    return {**selection, "plan": plan, "stop_reason": None}


def fit_refinement_budget(steps, reviewed_seconds, duration, interval, max_frames, *, strategy="gap_bisection"):
    if strategy == "gap_bisection":
        return gap_selection(steps, reviewed_seconds, duration, interval, max_frames)
    if strategy != "uniform":
        raise ValueError("Unknown refinement strategy.")
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
