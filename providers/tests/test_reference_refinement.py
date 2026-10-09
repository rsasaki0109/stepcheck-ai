"""Bounded planning tests, independent of any vision model or transport."""

import pytest

from stepcheck_providers.reference_refinement import fit_refinement_budget, plan_refinement


def steps(left=0, right=20, ambiguous=None):
    return [{"step_id": "a", "status": "observed", "evidence_seconds": [left]},
        {"step_id": "b", "status": "unknown", "evidence_seconds": ambiguous or []},
        {"step_id": "c", "status": "observed", "evidence_seconds": [right]}]


def test_fit_retains_anchors_and_cites_only_added_or_context_samples():
    result = fit_refinement_budget(steps(), [0, 10, 20], 21, 0.25, 4)
    assert result["chosen_interval_seconds"] == 8
    assert result["plan"]["sampled_seconds"] == [0, 8, 16, 20]
    assert result["plan"]["added_seconds"] == [8, 16]
    assert result["plan"]["target_step_ids"] == ["b"]
    assert result["attempts"][-1] == {"interval_seconds": 8, "status": "fits", "frames": 4}


def test_no_new_and_context_over_budget_stop_without_dropping_images():
    result = fit_refinement_budget(steps(), [0, 10, 20], 21, 0.25, 2)
    assert result["plan"] is None and result["stop_reason"] == "no_new_samples"
    result = fit_refinement_budget(steps(ambiguous=[10]), [0, 10, 20], 21, 0.25, 2)
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
    result = fit_refinement_budget(steps(), [0, 20], 21, 1e-308, 24)
    assert result["stop_reason"] == "refinement_budget_exhausted"
    assert len(result["attempts"]) == 16


@pytest.mark.parametrize("interval,budget", [(0, 24), (float("nan"), 24), (1, 1), (1, 97)])
def test_invalid_options_fail_before_planning(interval, budget):
    with pytest.raises(ValueError):
        fit_refinement_budget(steps(), [0, 20], 21, interval, budget)
