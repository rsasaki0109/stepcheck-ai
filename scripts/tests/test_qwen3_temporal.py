"""Temporal evidence must preserve source time and reject fabricated citations."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from diagnose_qwen3_temporal import check_time_tokens, parse_pairs, expected_pair_times
from stepcheck_providers.flow import VideoFrame
from stepcheck_providers import ImagePayload
from app.infrastructure.video import SampledVideo
from app.application.discover_flow_use_case import report_with_frames


class TemporalEvidenceTests(unittest.TestCase):
    def test_window_keeps_absolute_source_time(self):
        self.assertEqual(expected_pair_times([48, 49, 50, 51], 4), [12.125, 12.625])
        self.assertEqual(check_time_tokens("<12.1 seconds>x<12.6 seconds>", [48,49,50,51], 4, 2),
                         ["12.1", "12.6"])
        with self.assertRaises(ValueError):
            check_time_tokens("<0.1 seconds>x<0.6 seconds>", [48,49,50,51], 4, 2)

    def test_dropped_or_reordered_time_tokens_rejected(self):
        for text in ("<12.1 seconds>", "<12.6 seconds><12.1 seconds>"):
            with self.assertRaises(ValueError):
                check_time_tokens(text, [48,49,50,51], 4, 2)
        with self.assertRaises(ValueError):
            expected_pair_times([50,51,48,49], 4)

    def test_pair_citation_maps_both_real_source_frames(self):
        frames = [VideoFrame(i/4, ImagePayload(b"real-frame", "image/jpeg")) for i in range(52)]
        action = {"label": "動作", "reason": "根拠", "evidence_pair_ids": [1]}
        payload = {"title": "試験", "actions": [action], "limitations": ["未検証"]}
        detection = parse_pairs(json.dumps(payload), frames, [48,49,50,51], 4)
        self.assertEqual(detection.actions[0].evidence_seconds, [12.5, 12.75])
        for invalid in ([-1], [2], [1.5], [True]):
            action["evidence_pair_ids"] = invalid
            with self.assertRaises(ValueError):
                parse_pairs(json.dumps(payload), frames, [48,49,50,51], 4)

    def test_sparse_video_report_contains_only_supplied_frames(self):
        frames = [VideoFrame(i/4, ImagePayload(b"source", "image/jpeg")) for i in range(52)]
        indices = [48,50]
        raw = json.dumps({"title":"Sparse", "actions":[{"label":"Action", "reason":"Visible",
            "evidence_pair_ids":[0]}], "limitations":["Unverified"]})
        detection = parse_pairs(raw, frames, indices, 4)
        supplied = SampledVideo(13, [frames[i] for i in indices], 0.5)
        report = report_with_frames(detection, supplied, provider="qwen-local", source_sha256="test",
                                   analysis_mode="live", model="test")
        self.assertEqual(report["sampled_seconds"], [12,12.5])
        self.assertEqual([f["timestamp_seconds"] for f in report["frames"]], [12,12.5])
        self.assertEqual(report["actions"][0]["evidence_seconds"], [12,12.5])


if __name__ == "__main__":
    unittest.main()
