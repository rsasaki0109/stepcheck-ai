"""Real upload decoding, synthetic provider transport, and genuine recorded MCP replay."""

import base64
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from app.api.dependencies import get_provider
from app.api import video_routes
from app.config import Settings, get_settings
from app.main import create_app
from stepcheck_providers import VisionProvider
from stepcheck_providers.flow import FlowInferenceError
from stepcheck_providers.reference_flow import ReferenceJudgment

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs/assets/video-demo/new-video-transfer/source.webm"
REFERENCE = {"title": "Synthetic API fixture", "steps": [{"id": "a", "label": "A", "criterion": "Visible A"},
    {"id": "b", "label": "B", "criterion": "Visible B"}]}


class FixtureProvider(VisionProvider):
    name = "synthetic-test"
    supports_reference_flow = True
    def __init__(self):
        self.received = None
        self.mode = "forward"
    async def verify(self, request):
        return []
    async def verify_reference_flow(self, reference, frames, duration):
        self.received = (reference, frames, duration)
        if self.mode == "error":
            raise FlowInferenceError("Synthetic transport failure")
        times = [f.timestamp_seconds for f in frames]
        first, second = (times[-1], times[0]) if self.mode == "reverse" else (times[0], times[-1])
        return ReferenceJudgment(observations=[
            {"step_id": "a", "status": "observed", "reason": "Synthetic fixture", "uncertainty": "Not vision accuracy",
                "evidence_seconds": [0.1 if self.mode == "unseen" else first]},
            {"step_id": "a" if self.mode == "duplicate" else "b", "status": "unknown" if self.mode == "unknown" else "observed",
                "reason": "Synthetic fixture", "uncertainty": "Not vision accuracy",
                "evidence_seconds": [] if self.mode == "unknown" else [second]}])


@pytest.fixture
def configured():
    provider = FixtureProvider()
    settings = Settings(max_video_frames=3)
    app = create_app()
    app.dependency_overrides[get_provider] = lambda: provider
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        yield client, provider, settings


def upload(client, reference=REFERENCE, video=None, **data):
    return client.post("/api/video-flow/verify", files={"video": ("clip.webm", SOURCE.read_bytes() if video is None else video, "video/webm")},
        data={"reference_json": reference if isinstance(reference, str) else json.dumps(reference), **data})


def test_uploaded_reference_uses_real_source_images_and_preserves_labels(configured):
    client, provider, _ = configured
    status = client.get("/api/video-flow/status").json()
    assert status["reference_ready"] and not status["ready"]  # Independent optional capabilities.
    response = upload(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["analysis_mode"] == "live" and body["expected_procedure_supplied"] is True
    assert body["order_status"] == "supported_sample_order" and body["initial"] is None and body["workflow"] is None
    assert body["source_sha256"] == hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    reference, frames, duration = provider.received
    assert reference.steps[1].criterion == "Visible B" and duration == 32.036
    assert len(frames) == 3 and frames[-1].timestamp_seconds > 31
    assert base64.b64decode(body["frames"][0]["image_url"].split(",", 1)[1]) == frames[0].image.data
    assert frames[0].image.data.startswith(b"\xff\xd8")
    assert body["steps"][1]["label"] == "B" and "confidence" not in body["steps"][0]


@pytest.mark.parametrize("mode,order", [("unknown", "unknown"), ("reverse", "violated")])
def test_unknown_and_order_violations_are_not_forced_to_completion(configured, mode, order):
    client, provider, _ = configured
    provider.mode = mode
    body = upload(client).json()
    assert body["order_status"] == order
    if mode == "unknown":
        assert body["steps"][1]["status"] == "unknown" and body["steps"][1]["evidence_seconds"] == []


@pytest.mark.parametrize("mode", ["unseen", "duplicate", "error"])
def test_invalid_predictions_and_failed_inference_are_controlled_errors(configured, mode):
    client, provider, _ = configured
    provider.mode = mode
    assert upload(client).status_code == 502


def test_invalid_reference_and_uploads_do_not_invoke_vision(configured):
    client, provider, settings = configured
    for reference in ("not JSON", {"title": "Empty", "steps": []},
        {**REFERENCE, "steps": [REFERENCE["steps"][0]] * 2}):
        assert upload(client, reference, b"x").status_code == 422
    assert upload(client, video=b"").status_code == 400
    assert upload(client, video=b"invalid").status_code == 422
    for interval in ("nan", "inf", -1):
        assert upload(client, video=b"x", sample_interval_seconds=interval).status_code == 422
    settings.max_video_bytes = 5
    assert upload(client, video=b"longlong").status_code == 413
    assert provider.received is None


def test_mock_cannot_generate_reference_verdicts():
    with TestClient(create_app()) as client:
        assert not client.get("/api/video-flow/status").json()["reference_ready"]
        assert upload(client, video=b"x").status_code == 503


def test_two_actual_mcp_passes_replay_without_inference_and_keep_unknown_drying():
    provider = FixtureProvider()
    app = create_app()
    app.dependency_overrides[get_provider] = lambda: provider
    with TestClient(app) as client:
        response = client.get("/api/video-flow/reference-demo")
        assert response.status_code == 200, response.text
        body = response.json()
        saved = json.loads((ROOT / "docs/assets/video-demo/automatic-reference-workflow/verification.json").read_text(encoding="utf-8"))
        assert body["analysis_mode"] == "recorded_demo" and body["steps"] == saved["steps"]
        assert body["order_status"] == "unknown" and body["steps"][-1]["status"] == "unknown"
        assert body["initial"]["steps"][-1]["evidence_seconds"] == [26, 32]
        assert body["workflow"]["sampling_requests"] == 2
        assert len(body["frames"]) == 30 and body["sample_interval_seconds"] is None
        assert "CC BY-SA 2.0" in body["source_credit"]
        assert provider.received is None
        video = client.get("/api/video-flow/reference-demo/video", headers={"Range": "bytes=0-99"})
        assert video.status_code == 206 and len(video.content) == 100


def test_recorded_demo_rejects_changed_source_or_initial_before_decoding(tmp_path):
    assets = tmp_path / "automatic-reference-workflow"
    assets.mkdir()
    source = tmp_path / "new-video-transfer/source.webm"
    source.parent.mkdir()
    originals = ROOT / "docs/assets/video-demo/automatic-reference-workflow"
    for name in ("verification.json", "initial-verification.json"):
        (assets / name).write_bytes((originals / name).read_bytes())
    source.write_bytes(b"another video")
    video_routes.load_reference_demo.cache_clear()
    try:
        with patch.object(video_routes, "DEMO_ASSETS", tmp_path), patch.object(video_routes, "read_video_frame") as decode:
            with TestClient(create_app()) as client:
                assert client.get("/api/video-flow/reference-demo").status_code == 502
                source.write_bytes(SOURCE.read_bytes())
                initial = json.loads((assets / "initial-verification.json").read_text(encoding="utf-8"))
                initial["steps"][0]["reason"] = "Tampered prior observation"
                (assets / "initial-verification.json").write_text(json.dumps(initial))
                assert client.get("/api/video-flow/reference-demo").status_code == 502
            decode.assert_not_called()
    finally:
        video_routes.load_reference_demo.cache_clear()
