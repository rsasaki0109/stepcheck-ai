"""Evidence export safeguards and CLI transport fixtures, not recognition accuracy."""

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from render_reference_report import render_report, sampling_sheets, validate_bridge_report

ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "docs/assets/video-demo/automatic-reference-workflow"
VIDEO = ROOT / "docs/assets/video-demo/new-video-transfer/source.webm"
FINAL = json.loads((CAPTURE / "verification.json").read_text(encoding="utf-8"))
INITIAL = json.loads((CAPTURE / "initial-verification.json").read_text(encoding="utf-8"))


class ReferenceReportTest(unittest.TestCase):
    def test_wrong_source_unsampled_citation_and_forged_order_rejected_before_export(self):
        variants = [copy.deepcopy(FINAL) for _ in range(4)]
        variants[0]["source_sha256"] = "other video"
        variants[1]["steps"][0]["evidence_seconds"] = [1.234]
        variants[2]["order_status"] = "supported_sample_order"
        variants[3]["steps"][0]["status"] = "not_done"
        with tempfile.TemporaryDirectory() as directory, patch("render_reference_report.thumbnail") as decode:
            destination = Path(directory) / "report.html"
            for report in variants:
                with self.assertRaises(ValueError):
                    render_report(report, VIDEO, destination)
            decode.assert_not_called()
            self.assertFalse(destination.exists())

    def test_initial_provenance_and_known_verdicts_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory, patch("render_reference_report.thumbnail") as decode:
            destination = Path(directory) / "report.html"
            changed = copy.deepcopy(INITIAL)
            changed["steps"][0]["reason"] = "Different prior report"
            with self.assertRaisesRegex(ValueError, "provenance"):
                render_report(FINAL, VIDEO, destination, initial=changed)
            changed = copy.deepcopy(FINAL)
            changed["steps"][0]["reason"] = "Rewritten after follow-up"
            with self.assertRaisesRegex(ValueError, "previously observed"):
                render_report(changed, VIDEO, destination, initial=INITIAL)
            decode.assert_not_called()

    def test_report_text_cannot_inject_script_or_replace_template_tokens(self):
        report = copy.deepcopy(FINAL)
        report["steps"][0]["reason"] = '</script><script>alert("__DATA__")</script>'
        with tempfile.TemporaryDirectory() as directory, patch("render_reference_report.thumbnail", return_value="data:image/jpeg;base64,fixture"):
            destination = Path(directory) / "report.html"
            render_report(report, VIDEO, destination, linked_video=True)
            html = destination.read_text(encoding="utf-8")
            self.assertNotIn('</script><script>alert', html)
            self.assertIn('\\u003c/script\\u003e', html)
            self.assertIn('__DATA__', html)  # User text is substituted once only.
            self.assertIn('unknown_after_followup', html)
            self.assertNotIn('data:video/webm;base64,', html)

    def test_sampling_images_must_match_saved_request_hash_and_stay_local(self):
        with tempfile.TemporaryDirectory() as directory:
            bridge = Path(directory)
            (bridge / "sampling-0.png").write_bytes(b"fixture")
            request = {"images": [{"file": "sampling-0.png", "sha256": "wrong"}]}
            (bridge / "sampling-request.json").write_text(json.dumps(request))
            with self.assertRaisesRegex(ValueError, "differs"):
                sampling_sheets(bridge)
            request["images"][0].update(file="../other.png")
            (bridge / "sampling-request.json").write_text(json.dumps(request))
            with self.assertRaisesRegex(ValueError, "local filename"):
                sampling_sheets(bridge)

    def test_other_capture_or_failed_result_cannot_supply_input_images(self):
        with tempfile.TemporaryDirectory() as directory:
            bridge = Path(directory)
            result = {"is_error": False, "content": [{"type": "text", "text": json.dumps(INITIAL)}]}
            (bridge / "tool-result.json").write_text(json.dumps(result))
            with self.assertRaisesRegex(ValueError, "differ"):
                validate_bridge_report(bridge, FINAL)
            result["is_error"] = True
            (bridge / "tool-result.json").write_text(json.dumps(result))
            with self.assertRaisesRegex(ValueError, "failed"):
                validate_bridge_report(bridge, INITIAL)

    def test_cli_video_override_and_html_export_through_real_stdio(self):
        # Deliberately synthetic judgments; verifies plumbing, never semantic accuracy.
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            bridge = folder / "bridge"
            reference = folder / "reference.json"
            reference.write_text(json.dumps({"title": "Synthetic CLI transport fixture", "steps": [
                {"id": "a", "label": "Fixture A"}, {"id": "b", "label": "Fixture B"}]}))
            env = {**os.environ, "STEPCHECK_DEMO_VIDEO": str(folder / "nonexistent.webm")}
            with (folder / "log.txt").open("w", encoding="utf-8") as log:
                process = subprocess.Popen([sys.executable, str(ROOT / "scripts/run_flow_detection.py"),
                    "--video", str(VIDEO), "--bridge-dir", str(bridge), "--reference", str(reference),
                    "--auto-refine", "--interval", "20", "--output", str(bridge / "verification.json"),
                    "--reviewer", "synthetic transport fixture, not vision inference"],
                    stdout=log, stderr=log, env=env)
                try:
                    request = bridge / "pass-01/sampling-request.json"
                    deadline = time.monotonic() + 60
                    while not request.exists() and process.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.1)
                    self.assertTrue(request.exists(), (folder / "log.txt").read_text(encoding="utf-8"))
                    response = {"source_sha256": hashlib.sha256(VIDEO.read_bytes()).hexdigest(),
                        "observations": [{"step_id": step, "status": "observed", "reason": "Synthetic transport fixture",
                            "evidence_seconds": [timestamp], "uncertainty": "Not an accuracy assertion"}
                            for step, timestamp in (("a", 0), ("b", 20))]}
                    (bridge / "pass-01/response.json").write_text(json.dumps(response))
                    process.wait(timeout=60)
                    self.assertEqual(process.returncode, 0, (folder / "log.txt").read_text(encoding="utf-8"))
                    saved = json.loads((bridge / "verification.json").read_text(encoding="utf-8"))
                    self.assertEqual(saved["source_sha256"], response["source_sha256"])
                    self.assertEqual(saved["workflow"]["sampling_requests"], 1)
                    html = (bridge / "report.html").read_text(encoding="utf-8")
                    self.assertIn('data:video/webm;base64,', html)
                    self.assertIn('Synthetic CLI transport fixture', html)
                    self.assertFalse((bridge / "pass-02").exists())
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait()


if __name__ == "__main__":
    unittest.main()
