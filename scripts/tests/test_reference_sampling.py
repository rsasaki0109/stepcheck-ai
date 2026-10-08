"""MCP sampling transport and grounded-order validation; callbacks are synthetic fixtures."""

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


REFERENCE = {"title": "Fixture flow", "steps": [
    {"id": "a", "label": "A", "visible_criterion": "Fixture criterion A"},
    {"id": "b", "label": "B", "visible_criterion": "Fixture criterion B"},
]}


def observation(step, times, status="observed"):
    return {"step_id": step, "status": status, "reason": "Synthetic transport fixture",
            "evidence_seconds": times, "uncertainty": ""}


class ReferenceSamplingTest(unittest.TestCase):
    def test_real_mcp_transport_supplies_reference_and_images(self):
        async def check():
            calls = []
            response = {"source_sha256": hashlib.sha256(video_mcp.VIDEO.read_bytes()).hexdigest(),
                        "observations": [observation("a", [0]), observation("b", [20])]}

            async def callback(context, params):
                calls.append(params)
                blocks = params.messages[0].content
                self.assertEqual(params.include_context, "none")
                self.assertIn("Fixture criterion A", blocks[0].text)
                self.assertTrue(any(block.type == "image" for block in blocks))
                return CreateMessageResult(role="assistant", model="synthetic transport fixture",
                    content=TextContent(type="text", text=json.dumps(response)))

            with tempfile.TemporaryDirectory() as directory, patch.object(video_mcp,
                    "REFERENCE_REVIEW", Path(directory) / "verification.json"):
                async with Client(video_mcp.mcp, sampling_callback=callback) as client:
                    listed = await client.list_tools()
                    tool = next(t for t in listed.tools if t.name == "verify_reference_flow")
                    self.assertNotIn("completion", tool.input_schema["properties"])
                    result = await client.call_tool("verify_reference_flow", {
                        "reference": REFERENCE, "sample_interval_seconds": 20})
                    self.assertFalse(result.is_error)
                    report = json.loads(video_mcp.REFERENCE_REVIEW.read_text())
                    self.assertTrue(report["expected_procedure_supplied"])
                    self.assertEqual(report["order_status"], "supported_sample_order")
                    reverse = json.loads(video_mcp.REFERENCE_REVIEW.with_name("reverse-verification.json").read_text())
                    self.assertEqual(reverse["order_status"], "violated")
                    prior = video_mcp.REFERENCE_REVIEW.read_bytes()
                    response["observations"][1]["evidence_seconds"] = [1]
                    invalid = await client.call_tool("verify_reference_flow", {
                        "reference": REFERENCE, "sample_interval_seconds": 20})
                    self.assertTrue(invalid.is_error)
                    self.assertEqual(video_mcp.REFERENCE_REVIEW.read_bytes(), prior)
                    invalid_ref = await client.call_tool("verify_reference_flow", {
                        "reference": {"title": "Invalid", "steps": []}, "sample_interval_seconds": 20})
                    self.assertTrue(invalid_ref.is_error)
                    self.assertEqual(len(calls), 2)  # Invalid reference rejected before host sampling.
        asyncio.run(check())

    def test_unknown_and_overlapping_evidence_do_not_pass_order(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(video_mcp,
                "REFERENCE_REVIEW", Path(directory) / "verification.json"):
            for items in [[observation("a", [0]), observation("b", [], "unknown")],
                          [observation("a", [0, 2]), observation("b", [1])]]:
                report = video_mcp.save_reference_verification("fixture", REFERENCE,
                    [video_mcp.ReferenceObservation(**i) for i in items], [0, 1, 2], "test fixture")
                self.assertEqual(report["order_status"], "unknown")

    def test_bad_responses_preserve_saved_evidence(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(video_mcp,
                "REFERENCE_REVIEW", Path(directory) / "verification.json"):
            video_mcp.REFERENCE_REVIEW.write_text("previous evidence")
            source_hash = hashlib.sha256(video_mcp.VIDEO.read_bytes()).hexdigest()
            valid = {"source_sha256": source_hash,
                     "observations": [observation("a", [0]), observation("b", [20])]}
            invalid_answers = ["not JSON", json.dumps({**valid, "source_sha256": "wrong"}),
                json.dumps({**valid, "observations": [observation("a", [0])]}),
                json.dumps({**valid, "observations": [observation("a", [0]), observation("a", [20])]}),
                json.dumps({**valid, "observations": [observation("a", []), observation("b", [20])]}),
                json.dumps({**valid, "confidence": 0.99})]
            for answer in invalid_answers:
                with self.assertRaises(video_mcp.ToolError):
                    video_mcp.verify_reference_flow(REFERENCE, 20, CreateMessageResult(
                        role="assistant", model="fixture", content=TextContent(type="text", text=answer)))
                self.assertEqual(video_mcp.REFERENCE_REVIEW.read_text(), "previous evidence")
            self.assertFalse(video_mcp.REFERENCE_REVIEW.with_name("reverse-verification.json").exists())

    def test_malformed_reference_is_rejected(self):
        for steps in [None, [1], [{"id": "a"}], [{"id": "a", "label": " "}],
                      [{"id": "a", "label": "A"}, {"id": "a", "label": "A"}]]:
            with self.assertRaises(video_mcp.ToolError):
                video_mcp.validate_reference({"title": "Test", "steps": steps})


if __name__ == "__main__":
    unittest.main()
