"""Flow validation and real MCP sampling transport; no simulated VLM accuracy claim."""

import asyncio
import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from mcp import Client
from mcp.types import CreateMessageResult, TextContent

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from video_discovery import Detection, build_flow
import video_mcp


def detection(actions):
    return Detection(title="test", actions=actions, limitations=["sampled observations"])


def action(label, times):
    return {"label": label, "reason": "visible test evidence", "evidence_seconds": times}


class DiscoveryTest(unittest.TestCase):
    def test_order_is_derived_from_evidence_and_repetitions_are_preserved(self):
        result = build_flow(detection([action("A", [3]), action("A", [0]), action("B", [1])]), [0, 1, 3], 4)
        self.assertEqual([item["label"] for item in result["actions"]], ["A", "B", "A"])
        self.assertEqual([item["id"] for item in result["actions"]], [1, 2, 3])
        self.assertTrue(all(edge["status"] == "sampled_before" for edge in result["transitions"]))

    def test_overlapping_evidence_does_not_claim_strict_order(self):
        result = build_flow(detection([action("A", [0, 2]), action("B", [1])]), [0, 1, 2], 4)
        self.assertEqual(result["transitions"][0]["status"], "ambiguous")
        tied = build_flow(detection([action("A", [0]), action("B", [0])]), [0], 4)
        self.assertEqual(tied["transitions"][0]["status"], "ambiguous")

    def test_unreviewed_or_invalid_evidence_is_rejected(self):
        for timestamp in [0.5, float("nan"), float("inf"), -1, 99]:
            with self.assertRaises(ValueError):
                build_flow(detection([action("A", [timestamp])]), [0, 1], 4)
        with self.assertRaises(ValueError):
            build_flow(detection([]), [99], 4)
        self.assertEqual(build_flow(detection([]), [0], 4)["actions"], [])

    def test_sampling_roundtrip_has_images_and_no_expected_procedure(self):
        async def check():
            calls = []
            response = detection([action("Visible action", [0])]).model_dump_json()
            async def callback(context, params):
                blocks = params.messages[0].content
                calls.append(params)
                self.assertEqual(params.include_context, "none")
                self.assertTrue(any(block.type == "image" for block in blocks))
                for block in blocks:
                    if block.type == "image":
                        self.assertTrue(base64.b64decode(block.data).startswith(b"\x89PNG"))
                # Deliberately synthetic callback: transport/validation test only.
                return CreateMessageResult(role="assistant", model="synthetic transport test",
                    content=TextContent(type="text", text=response))
            with tempfile.TemporaryDirectory() as directory, patch.object(video_mcp, "DETECTED_FLOW", Path(directory) / "flow.json"), patch.object(video_mcp, "steps", side_effect=AssertionError("Expected steps must not be read")):
                async with Client(video_mcp.mcp, sampling_callback=callback) as client:
                    listed = await client.list_tools()
                    tool = next(tool for tool in listed.tools if tool.name == "detect_flow")
                    self.assertNotIn("completion", tool.input_schema["properties"])
                    result = await client.call_tool("detect_flow", {"sample_interval_seconds": 20})
                    self.assertFalse(result.is_error)
                    saved = json.loads(video_mcp.DETECTED_FLOW.read_text(encoding="utf-8"))
                    self.assertFalse(saved["expected_procedure_supplied"])
                    self.assertEqual(saved["actions"][0]["label"], "Visible action")
                    self.assertEqual(len(calls), 1)
                    prior = video_mcp.DETECTED_FLOW.read_bytes()
                    invalid = await client.call_tool("record_detected_flow", {
                        "reviewer": "test", "detection": detection([action("A", [1])]).model_dump(),
                        "reviewed_seconds": [0],
                    })
                    self.assertTrue(invalid.is_error)
                    self.assertEqual(video_mcp.DETECTED_FLOW.read_bytes(), prior)
                    for response in ["not JSON", detection([action("Invented evidence", [1])]).model_dump_json()]:
                        invalid = await client.call_tool("detect_flow", {"sample_interval_seconds": 20})
                        self.assertTrue(invalid.is_error)
                        self.assertEqual(video_mcp.DETECTED_FLOW.read_bytes(), prior)
        asyncio.run(check())

    def test_sampling_budget_is_bounded(self):
        for interval in [0, -1, float("nan"), 0.001]:
            with self.assertRaises(video_mcp.ToolError):
                video_mcp.sample_times(interval)


if __name__ == "__main__":
    unittest.main()
