"""Notebook validity and viewer evidence/source safeguards, without model inference."""

import ast
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_local_video_flow


class ColabNotebookTest(unittest.TestCase):
    def test_failed_retry_cannot_leave_previous_success_viewer(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            output.mkdir()
            for name in ("flow.json", "viewer.html", "execution.json"):
                (output / name).write_text("previous successful run")
            video = Path(directory) / "clip.webm"
            video.write_bytes(b"test source")
            provider = SimpleNamespace(last_raw_response="invalid model JSON",
                discover_flow=AsyncMock(side_effect=ValueError("invalid inference")))
            sampled = SimpleNamespace(frames=[], duration_seconds=2)
            with patch.object(run_local_video_flow, "sample_video", return_value=sampled):
                with self.assertRaises(ValueError):
                    asyncio.run(run_local_video_flow.run_local_flow(video, output, provider=provider))
            self.assertFalse((output / "flow.json").exists())
            self.assertFalse((output / "viewer.html").exists())
            self.assertFalse((output / "execution.json").exists())
            self.assertEqual((output / "model-response.txt").read_text(), "invalid model JSON")

    def test_notebook_code_is_valid_and_contains_no_canned_inference_outputs(self):
        notebook = json.loads((run_local_video_flow.ROOT / "notebooks/stepcheck_local_vlm.ipynb").read_text(encoding="utf-8"))
        self.assertEqual(notebook["nbformat"], 4)
        for cell in notebook["cells"]:
            if cell["cell_type"] == "code":
                compile("".join(cell["source"]), "colab cell", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
                self.assertEqual(cell["outputs"], [])
                self.assertIsNone(cell["execution_count"])

    def test_viewer_rejects_other_source_and_escapes_model_text(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "clip.webm"
            video.write_bytes(b"test source")
            report = {"source_sha256": "wrong"}
            destination = Path(directory) / "viewer.html"
            with self.assertRaises(ValueError):
                run_local_video_flow.render_viewer(report, video, destination)
            report.update(source_sha256=hashlib.sha256(video.read_bytes()).hexdigest(),
                          title='</script><script>alert("unsafe")</script>__SOURCE__')
            run_local_video_flow.render_viewer(report, video, destination)
            html = destination.read_text(encoding="utf-8")
            self.assertNotIn('</script><script>alert', html)
            self.assertIn('\\u003c/script\\u003e', html)
            self.assertIn('__SOURCE__', html)  # model text is not re-substituted


if __name__ == "__main__":
    unittest.main()
