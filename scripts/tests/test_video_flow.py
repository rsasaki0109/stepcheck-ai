"""Behavioral checks for chronological evidence and independently specified flow."""

import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_video_flow import ROOT, check_flow


class FlowCheckTest(unittest.TestCase):
    def setUp(self):
        self.flow = json.loads((ROOT / "examples/handwashing-flow.json").read_text(encoding="utf-8"))
        self.review = json.loads((ROOT / "docs/assets/video-demo/review.json").read_text(encoding="utf-8"))

    def test_real_video_order_is_consistent_but_complete_flow_is_unknown(self):
        result = check_flow(self.flow, self.review)
        self.assertEqual(result["observed_step_order"], [2, 3, 4, 5, 6])
        self.assertEqual(result["observed_order_status"], "consistent")
        self.assertEqual(result["overall_status"], "unknown")
        self.assertEqual(result["unverified_steps"], [1])
        self.assertEqual([edge["status"] for edge in result["transitions"]],
                         ["unknown", "consistent", "consistent", "consistent", "consistent"])

    def test_reversed_rinse_and_dry_times_are_a_violation(self):
        review = copy.deepcopy(self.review)
        review["steps"][4]["evidence_seconds"] = [10.0]
        result = check_flow(self.flow, review)
        self.assertEqual(result["overall_status"], "violated")
        self.assertIn([4, 5], result["inversions"])
        self.assertEqual(result["transitions"][3]["status"], "violated")

    def test_tied_confirmations_do_not_prove_an_order(self):
        review = copy.deepcopy(self.review)
        review["steps"][4]["evidence_seconds"] = [12.5]
        result = check_flow(self.flow, review)
        self.assertEqual(result["observed_order_status"], "ambiguous")
        self.assertEqual(result["overall_status"], "unknown")

    def test_a_missing_middle_step_stays_unknown(self):
        review = copy.deepcopy(self.review)
        review["steps"][3]["status"] = "unknown"
        result = check_flow(self.flow, review)
        self.assertIn(4, result["unverified_steps"])
        self.assertEqual(result["overall_status"], "unknown")
        self.assertEqual(result["transitions"][2]["status"], "unknown")
        self.assertEqual(result["transitions"][3]["status"], "unknown")

    def test_future_results_are_not_revealed_early(self):
        result = check_flow(self.flow, self.review, through_seconds=1.0)
        self.assertEqual(result["observed_step_order"], [2])
        self.assertEqual(result["overall_status"], "pending")
        self.assertEqual(result["steps"][2]["status"], "pending")

    def test_all_observed_in_order_can_verify_the_flow(self):
        review = copy.deepcopy(self.review)
        # Synthetic positive fixture; this does not alter the actual video review.
        review["steps"][0]["status"] = "completed"
        review["steps"][0]["evidence_seconds"] = [0.1]
        self.assertEqual(check_flow(self.flow, review)["overall_status"], "verified")
