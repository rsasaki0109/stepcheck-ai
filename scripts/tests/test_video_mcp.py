"""Integration checks for real MCP video frames and observation persistence."""

import asyncio
import base64
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from mcp import Client
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import video_mcp
import generate_readme_gif


class VideoMCPTest(unittest.TestCase):
    def test_frame_and_review_roundtrip(self):
        async def check():
            source = json.loads((video_mcp.ASSETS / "review.json").read_text(encoding="utf-8"))
            with tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / "review.json"
                with patch.object(video_mcp, "REVIEW", destination):
                    async with Client(video_mcp.mcp) as client:
                        frame = await client.call_tool("read_frame", {"timestamp_seconds": 0.3})
                        self.assertFalse(frame.is_error)
                        block = next(block for block in frame.content if block.type == "image")
                        self.assertEqual(block.mime_type, "image/png")
                        self.assertTrue(base64.b64decode(block.data).startswith(b"\x89PNG\r\n\x1a\n"))
                        observations = [{key: value for key, value in step.items() if key != "text"}
                                        for step in source["steps"]]
                        result = await client.call_tool("record_review", {
                            "reviewer": "integration test replay", "observations": observations,
                        })
                        self.assertFalse(result.is_error)
                        saved = json.loads(destination.read_text(encoding="utf-8"))
                        self.assertEqual(saved["source_sha256"], hashlib.sha256(video_mcp.VIDEO.read_bytes()).hexdigest())
                        self.assertEqual(saved["steps"], source["steps"])
                        order = await client.call_tool("check_flow")
                        self.assertFalse(order.is_error)
                        order_report = json.loads(destination.with_name("order-review.json").read_text(encoding="utf-8"))
                        self.assertEqual(order_report["observed_order_status"], "consistent")
                        self.assertEqual(order_report["overall_status"], "unknown")
                        original = destination.read_bytes()
                        duplicate = [observations[0]] * len(observations)
                        invalid = await client.call_tool("record_review", {
                            "reviewer": "test", "observations": duplicate,
                        })
                        self.assertTrue(invalid.is_error)
                        self.assertEqual(destination.read_bytes(), original)
                        observations[0] = {**observations[0], "evidence_seconds": [999]}
                        invalid = await client.call_tool("record_review", {
                            "reviewer": "test", "observations": observations,
                        })
                        self.assertTrue(invalid.is_error)
                        self.assertEqual(destination.read_bytes(), original)
        asyncio.run(check())

    def test_out_of_range_frame_is_rejected(self):
        async def check():
            async with Client(video_mcp.mcp) as client:
                for timestamp in (-1, 999):
                    result = await client.call_tool("read_frame", {"timestamp_seconds": timestamp})
                    self.assertTrue(result.is_error)
                    self.assertFalse(any(block.type == "image" for block in result.content))
        asyncio.run(check())

    def test_renderer_rejects_changed_source_before_decoding(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = Path(directory)
            (assets / "source.webm").write_bytes(b"different video")
            (assets / "review.json").write_text(
                json.dumps({"source_sha256": "not-the-source-hash"}), encoding="utf-8",
            )
            with patch.object(generate_readme_gif, "ASSETS", assets), patch.object(
                generate_readme_gif.subprocess, "run",
            ) as decode:
                with self.assertRaisesRegex(ValueError, "differs from the reviewed source"):
                    generate_readme_gif.main()
                decode.assert_not_called()

    def test_region_validation_rejects_wrong_source_and_bad_boxes(self):
        report = json.loads((video_mcp.ASSETS / "review.json").read_text(encoding="utf-8"))
        regions = json.loads((video_mcp.ASSETS / "regions.json").read_text(encoding="utf-8"))
        generate_readme_gif.validate_regions(regions, report)
        wrong_source = {**regions, "source_sha256": "wrong-video"}
        with self.assertRaisesRegex(ValueError, "different reviewed video"):
            generate_readme_gif.validate_regions(wrong_source, report)
        for bounds in [[-0.1, 0.1, 0.9, 0.9], [0.8, 0.1, 0.2, 0.9]]:
            invalid = copy.deepcopy(regions)
            invalid["panels"][0]["keyframes"][0]["bbox"] = bounds
            with self.assertRaises(ValueError):
                generate_readme_gif.validate_regions(invalid, report)
        unknown_step = copy.deepcopy(regions)
        unknown_step["panels"][0]["steps"] = [1]
        with self.assertRaisesRegex(ValueError, "Only observed steps"):
            generate_readme_gif.validate_regions(unknown_step, report)

    def test_transition_without_visible_region_does_not_change_pixels(self):
        regions = json.loads((video_mcp.ASSETS / "regions.json").read_text(encoding="utf-8"))
        bounds, label = generate_readme_gif.region_at(regions["panels"][0], 0.85)
        self.assertIsNone(bounds)
        source = Image.new("RGB", (480, 360), "#476385")
        overlay = generate_readme_gif.evidence_overlay(source, bounds, label)
        self.assertEqual(source.tobytes(), overlay.tobytes())

    def test_unreviewed_frames_have_no_invented_region(self):
        regions = json.loads((video_mcp.ASSETS / "regions.json").read_text(encoding="utf-8"))
        bounds, _ = generate_readme_gif.region_at(regions["panels"][0], 2.0)
        self.assertIsNone(bounds)


if __name__ == "__main__":
    unittest.main()
