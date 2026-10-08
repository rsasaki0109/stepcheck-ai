"""Refinement grounding, history, and real MCP transport; synthetic vision fixtures only."""

import asyncio
import copy
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


def observation(step, status, times):
    return video_mcp.ReferenceObservation(step_id=step, status=status,
        reason="Synthetic validation fixture, not model accuracy", evidence_seconds=times)


def prior():
    reference = {"title": "Fixture", "steps": [
        {"id": "left", "label": "Left anchor"},
        {"id": "target", "label": "Unknown target"},
        {"id": "right", "label": "Right anchor"}]}
    return video_mcp.build_reference_verification("original fixture reviewer", reference,
        [observation("left", "observed", [19.5]), observation("target", "unknown", [21, 21.75]),
         observation("right", "observed", [22.5])], [19.5, 20.25, 21, 21.75, 22.5], "fixture")


def completion(previous, items):
    return CreateMessageResult(role="assistant", model="synthetic follow-up reviewer",
        content=TextContent(type="text", text=json.dumps({"source_sha256": previous["source_sha256"],
            "observations": [s.model_dump() for s in items]})))


class RefinementTest(unittest.TestCase):
    def test_real_sampling_roundtrip_preserves_confirmed_steps_and_history(self):
        async def check():
            previous = prior()
            async def callback(context, params):
                blocks = params.messages[0].content
                self.assertEqual(params.include_context, "none")
                self.assertIn('"id": "target"', blocks[0].text)
                self.assertNotIn('"id": "left"', blocks[0].text)
                self.assertNotIn("original fixture reviewer", blocks[0].text)
                self.assertTrue(any(b.type == "image" for b in blocks))
                return completion(previous, [observation("target", "observed", [21.5])])
            with tempfile.TemporaryDirectory() as directory, patch.object(video_mcp,
                    "REFERENCE_REVIEW", Path(directory) / "verification.json"):
                async with Client(video_mcp.mcp, sampling_callback=callback) as client:
                    listed = await client.list_tools()
                    tool = next(t for t in listed.tools if t.name == "refine_reference_flow")
                    self.assertNotIn("completion", tool.input_schema["properties"])
                    result = await client.call_tool("refine_reference_flow", {"previous": previous})
                    self.assertFalse(result.is_error)
                saved = json.loads(video_mcp.REFERENCE_REVIEW.read_text())
                before = json.loads(video_mcp.REFERENCE_REVIEW.with_name("before-verification.json").read_text())
                self.assertEqual(before, previous)
                self.assertEqual(saved["steps"][0], previous["steps"][0])
                self.assertEqual(saved["steps"][2], previous["steps"][2])
                self.assertEqual(saved["order_status"], "supported_sample_order")
                self.assertEqual(saved["refinement"]["prior_order_status"], "unknown")
                self.assertEqual(saved["refinement"]["reviewer"], "synthetic follow-up reviewer")
                reverse = json.loads(video_mcp.REFERENCE_REVIEW.with_name("reverse-verification.json").read_text())
                self.assertEqual(reverse["order_status"], "violated")
        asyncio.run(check())

    def test_refinement_does_not_force_unknown_to_observed(self):
        previous = prior()
        with tempfile.TemporaryDirectory() as directory, patch.object(video_mcp,
                "REFERENCE_REVIEW", Path(directory) / "verification.json"):
            report = video_mcp.refine_reference_flow(previous, completion=completion(previous,
                [observation("target", "unknown", [])]))
            self.assertEqual(report["order_status"], "unknown")
            self.assertEqual(report["steps"][1]["status"], "unknown")

    def test_unsupported_citations_and_changes_to_confirmed_steps_leave_outputs_unchanged(self):
        previous = prior()
        with tempfile.TemporaryDirectory() as directory, patch.object(video_mcp,
                "REFERENCE_REVIEW", Path(directory) / "verification.json"):
            video_mcp.REFERENCE_REVIEW.write_text("existing report")
            for items in [[observation("target", "observed", [20.25])],
                          [observation("target", "observed", [21.5]), observation("left", "unknown", [])],
                          [observation("target", "observed", [21.5])] * 2,
                          [observation("target", "observed", [])], []]:
                with self.assertRaises(video_mcp.ToolError):
                    video_mcp.refine_reference_flow(previous, completion=completion(previous, items))
                self.assertEqual(video_mcp.REFERENCE_REVIEW.read_text(), "existing report")
                self.assertFalse(video_mcp.REFERENCE_REVIEW.with_name("before-verification.json").exists())

    def test_windows_come_from_neighbor_evidence_and_requests_are_bounded(self):
        previous = prior()
        plan = video_mcp.refinement_plan(previous, 0.25, 24)
        self.assertEqual(plan["windows"], [{"step_id": "target", "start_seconds": 19.5, "end_seconds": 22.5}])
        self.assertIn(21.5, plan["added_seconds"])
        self.assertNotIn(20.25, plan["sampled_seconds"])
        for interval, budget in [(0, 24), (float("nan"), 24), (0.000001, 24), (0.25, 2), (0.25, 97), (3, 24)]:
            with self.assertRaises(video_mcp.ToolError):
                video_mcp.refinement_plan(previous, interval, budget)

    def test_changed_source_and_inconsistent_prior_reports_are_rejected(self):
        previous = prior()
        invalid = copy.deepcopy(previous)
        invalid["order_status"] = "supported_sample_order"
        for report in [invalid, {**previous, "source_sha256": "other video"},
                       {**previous, "expected_procedure_supplied": False}]:
            with self.assertRaises(video_mcp.ToolError):
                video_mcp.refinement_plan(report, 0.25, 24)

    def test_contradictory_anchors_do_not_make_an_empty_ordered_gap(self):
        previous = prior()
        observations = [observation("left", "observed", [22.5]),
            observation("target", "unknown", []), observation("right", "observed", [19.5])]
        report = video_mcp.build_reference_verification("fixture", previous["reference"],
            observations, [19.5, 22.5], "fixture")
        plan = video_mcp.refinement_plan(report, 2, 24)
        self.assertEqual(plan["windows"][0]["start_seconds"], 0)
        self.assertEqual(plan["windows"][0]["end_seconds"], report["duration_seconds"] - 0.1)


if __name__ == "__main__":
    unittest.main()
