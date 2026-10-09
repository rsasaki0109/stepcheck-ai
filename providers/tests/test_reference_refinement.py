"""Bounded planning tests, independent of any vision model or transport."""

import pytest
import json
from pathlib import Path

from stepcheck_providers.reference_refinement import fit_refinement_budget, plan_refinement


def steps(left=0, right=20, ambiguous=None):
    return [{"step_id": "a", "status": "observed", "evidence_seconds": [left]},
        {"step_id": "b", "status": "unknown", "evidence_seconds": ambiguous or []},
        {"step_id": "c", "status": "observed", "evidence_seconds": [right]}]


def test_fit_retains_anchors_and_cites_only_added_or_context_samples():
    result = fit_refinement_budget(steps(), [0, 10, 20], 21, 0.25, 4, strategy="uniform")
    assert result["chosen_interval_seconds"] == 8
    assert result["plan"]["sampled_seconds"] == [0, 8, 16, 20]
    assert result["plan"]["added_seconds"] == [8, 16]
    assert result["plan"]["target_step_ids"] == ["b"]
    assert result["attempts"][-1] == {"interval_seconds": 8, "status": "fits", "frames": 4}


def test_no_new_and_context_over_budget_stop_without_dropping_images():
    result = fit_refinement_budget(steps(), [0, 10, 20], 21, 0.25, 2)
    assert result["plan"] is None and result["stop_reason"] == "no_new_samples"
    result = fit_refinement_budget(steps(ambiguous=[10]), [0, 10, 20], 21, 0.25, 2, strategy="uniform")
    assert result["plan"] is None and result["stop_reason"] == "refinement_budget_exhausted"
    assert len(result["attempts"]) == 16


def test_contradictory_anchors_search_full_video_instead_of_assuming_order():
    plan = plan_refinement(steps(20, 0), [0, 20], 21, 4, 10)
    assert plan["windows"] == [{"step_id": "b", "start_seconds": 0, "end_seconds": 20.9}]
    assert plan["added_seconds"] == [4, 8, 12, 16, 20.9]


def test_near_tail_float_rounding_does_not_invent_a_new_review_time():
    duration = 14.041  # duration - 0.1 has more than six decimal places in binary.
    prior = [{"step_id": "a", "status": "observed", "evidence_seconds": [0]},
        {"step_id": "b", "status": "unknown", "evidence_seconds": []}]
    result = fit_refinement_budget(prior, [0, 13.941], duration, 20, 2)
    assert result["stop_reason"] == "no_new_samples"


def test_extremely_small_positive_interval_is_bounded_without_overflow():
    result = fit_refinement_budget(steps(), [0, 20], 21, 1e-308, 24, strategy="uniform")
    assert result["stop_reason"] == "refinement_budget_exhausted"
    assert len(result["attempts"]) == 16


@pytest.mark.parametrize("interval,budget", [(0, 24), (float("nan"), 24), (1, 1), (1, 97), (1, 2.5), (1, float("nan"))])
def test_invalid_options_fail_before_planning(interval, budget):
    with pytest.raises(ValueError):
        fit_refinement_budget(steps(), [0, 20], 21, interval, budget)


def test_gap_bisection_uses_old_reviewed_times_and_fills_budget():
    result = fit_refinement_budget(steps(), [0, 10, 20], 21, 0.25, 4)
    assert result["chosen_interval_seconds"] is None
    assert result["plan"]["sampled_seconds"] == [0, 5, 15, 20]
    assert result["plan"]["coverage"] == {"before_max_gap_seconds": 10, "after_max_gap_seconds": 5,
        "requested_max_gap_seconds": 0.25, "budget_limited": True}


def test_gap_bisection_preserves_ambiguous_context_and_stops_at_requested_spacing():
    result = fit_refinement_budget(steps(ambiguous=[10]), [0, 10, 20], 21, 5, 12)
    assert result["plan"]["sampled_seconds"] == [0, 5, 10, 15, 20]
    assert not result["plan"]["coverage"]["budget_limited"]
    result = fit_refinement_budget(steps(ambiguous=[10]), [0, 10, 20], 21, .25, 2)
    assert result["plan"] is None and result["stop_reason"] == "refinement_budget_exhausted"


def test_gap_bisection_is_bounded_for_tiny_intervals_and_handles_microsecond_rounding():
    result = fit_refinement_budget(steps(), [0, 20], 21, 1e-308, 24)
    assert len(result["plan"]["sampled_seconds"]) == 24
    result = fit_refinement_budget(steps(0, 0.000001), [0, 0.000001], 1, 1e-308, 96)
    assert result["plan"] is None and result["stop_reason"] == "no_new_samples"
    result = fit_refinement_budget(steps(0, .3), [0, .1, .2, .3], 1, .1, 96)
    assert result["plan"] is None  # Floating-point .3-.2 is not a genuinely wider gap.


def test_more_budget_never_increases_scoped_review_gap_and_does_not_repeat_prior_frames():
    previous = 20
    for budget in range(3, 16):
        plan = fit_refinement_budget(steps(), [0, 20], 21, .25, budget)["plan"]
        assert len(plan["sampled_seconds"]) <= budget
        assert not set(plan["added_seconds"]) & {0, 20}
        assert plan["coverage"]["after_max_gap_seconds"] <= previous
        previous = plan["coverage"]["after_max_gap_seconds"]


def test_recorded_initial_gap_coverage_improves_without_action_names_or_correct_times():
    root = Path(__file__).resolve().parents[2]
    report = json.loads((root / "docs/assets/video-demo/qwen3-web-auto-small/api-response.json").read_text(encoding="utf-8"))
    prior = report["initial"]
    plan = fit_refinement_budget(prior["steps"], prior["sampled_seconds"], report["duration_seconds"], .25, 12)["plan"]
    assert len(plan["sampled_seconds"]) == 12 and len(plan["added_seconds"]) == 7
    assert plan["coverage"]["after_max_gap_seconds"] < plan["coverage"]["before_max_gap_seconds"]
    assert plan["coverage"]["after_max_gap_seconds"] <= 1.451637
    renamed = [{**s, "label": "unrelated label", "step_id": str(i)} for i, s in enumerate(prior["steps"])]
    same = fit_refinement_budget(renamed, prior["sampled_seconds"], report["duration_seconds"], .25, 12)["plan"]
    assert same["sampled_seconds"] == plan["sampled_seconds"]
