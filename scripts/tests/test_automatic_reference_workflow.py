"""Real MCP dependency round trips with synthetic replies: orchestration, not accuracy."""

import asyncio
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from mcp import Client
from mcp.types import CreateMessageResult, TextContent

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import video_mcp


REFERENCE = {"title": "Workflow fixture", "steps": [
    {"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}]}


def observed(step, times, status="observed"):
    return {"step_id": step, "status": status, "reason": "Synthetic transport fixture",
            "evidence_seconds": times, "uncertainty": ""}


class AutomaticWorkflowTest(unittest.TestCase):
    def run_workflow(self, initial, followup, *, budget=4, invalid=False):
        async def check():
            calls = []
            async def callback(context, params):
                calls.append(params)
                self.assertEqual(params.include_context, "none")
                self.assertTrue(any(b.type == "image" for b in params.messages[0].content))
                items = initial if len(calls) == 1 else followup
                response = items if isinstance(items, str) else json.dumps({
                    "source_sha256": hashlib.sha256(video_mcp.VIDEO.read_bytes()).hexdigest(),
                    "observations": items})
                return CreateMessageResult(role="assistant", model=f"synthetic pass {len(calls)}",
                    content=TextContent(type="text", text=response))
            with tempfile.TemporaryDirectory() as directory, patch.object(video_mcp,
                    "REFERENCE_REVIEW", Path(directory) / "verification.json"):
                if invalid:
                    video_mcp.REFERENCE_REVIEW.write_text("prior successful result")
                async with Client(video_mcp.mcp, sampling_callback=callback) as client:
                    listed = await client.list_tools()
                    schema = next(t for t in listed.tools if t.name == "verify_reference_flow_auto").input_schema
                    for hidden in ("completion", "initial", "selection"):
                        self.assertNotIn(hidden, schema["properties"])
                    result = await client.call_tool("verify_reference_flow_auto", {
                        "reference": REFERENCE, "sample_interval_seconds": 20, "max_frames": budget})
                if invalid:
                    self.assertTrue(result.is_error)
                    self.assertEqual(video_mcp.REFERENCE_REVIEW.read_text(), "prior successful result")
                    self.assertFalse(video_mcp.REFERENCE_REVIEW.with_name("initial-verification.json").exists())
                    self.assertFalse(video_mcp.REFERENCE_REVIEW.with_name("before-verification.json").exists())
                    return None, calls
                self.assertFalse(result.is_error)
                saved = json.loads(video_mcp.REFERENCE_REVIEW.read_text())
                first = json.loads(video_mcp.REFERENCE_REVIEW.with_name("initial-verification.json").read_text())
                if len(calls) == 2:
                    self.assertEqual(first, json.loads(video_mcp.REFERENCE_REVIEW.with_name("before-verification.json").read_text()))
                    self.assertEqual(first["steps"][0], saved["steps"][0])
                    self.assertEqual(first["steps"][2], saved["steps"][2])
                return saved, calls
        return asyncio.run(check())

    def test_one_call_drives_two_sampling_rounds_and_fits_budget(self):
        saved, calls = self.run_workflow([observed("a", [0]), observed("b", [], "unknown"), observed("c", [20])],
            [observed("b", [10])])
        self.assertEqual(len(calls), 2)
        self.assertEqual(saved["order_status"], "supported_sample_order")
        self.assertEqual(saved["workflow"]["stop_reason"], "no_unknown_steps")
        selection = saved["workflow"]["interval_selection"]
        self.assertIsNone(selection["chosen_interval_seconds"])
        self.assertEqual(selection["strategy"], "gap_bisection")
        self.assertEqual(selection["plan"]["sampled_seconds"], [0, 5, 10, 20])
        self.assertTrue(all(a["status"] == "over_budget" for a in selection["attempts"][:-1]))
        self.assertEqual(len(selection["plan"]["sampled_seconds"]), 4)
        self.assertNotIn('"id": "a"', calls[1].messages[0].content[0].text)

    def test_unknown_after_followup_stops_instead_of_repeated_sampling(self):
        saved, calls = self.run_workflow([observed("a", [0]), observed("b", [], "unknown"), observed("c", [20])],
            [observed("b", [], "unknown")])
        self.assertEqual(len(calls), 2)
        self.assertEqual(saved["order_status"], "unknown")
        self.assertEqual(saved["workflow"]["stop_reason"], "unknown_after_followup")
        self.assertEqual(saved["workflow"]["unknown_step_ids"], ["b"])

    def test_no_unknowns_skips_followup_even_when_order_is_violated(self):
        saved, calls = self.run_workflow([observed("a", [20]), observed("b", [0]), observed("c", [22.903])], None)
        self.assertEqual(len(calls), 1)
        self.assertEqual(saved["order_status"], "violated")
        self.assertEqual(saved["workflow"]["stop_reason"], "no_unknown_steps")

    def test_no_new_samples_stops_without_violating_budget(self):
        saved, calls = self.run_workflow([observed("a", [0]), observed("b", [], "unknown"), observed("c", [20])], None,
            budget=2)
        self.assertEqual(len(calls), 1)
        self.assertEqual(saved["order_status"], "unknown")
        self.assertEqual(saved["workflow"]["stop_reason"], "no_new_samples")

    def test_bad_initial_or_followup_does_not_replace_saved_results(self):
        self.run_workflow("not JSON", None, invalid=True)
        initial = [observed("a", [0]), observed("b", [], "unknown"), observed("c", [20])]
        for response in ("not JSON", [observed("b", [1])], [observed("a", [8])]):
            self.run_workflow(initial, response, invalid=True)


if __name__ == "__main__":
    unittest.main()
