"""Real uploaded video decoding with synthetic provider results, plus recorded demo."""

import base64
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from app.api.dependencies import get_provider
from app.api import video_routes
from app.config import Settings, get_settings
from app.main import create_app
from stepcheck_providers import VisionProvider
from stepcheck_providers.flow import Detection, FlowInferenceError

SOURCE = Path(__file__).resolve().parents[2] / "docs/assets/video-demo/source.webm"


class TestVisionProvider(VisionProvider):
    """Only a test double; all JPEG frame bytes come from real FFmpeg decoding."""
    __test__ = False
    name = "synthetic-test"
    supports_flow = True

    def __init__(self, evidence=None):
        self.seen_frames = []
        self.evidence = evidence

    async def verify(self, request):
        return []

    async def discover_flow(self, frames, duration_seconds):
        self.seen_frames = frames
        return Detection(title="Synthetic test observations", actions=[
            {"label": "Test action", "reason": "Synthetic provider contract test",
             "evidence_seconds": self.evidence if self.evidence is not None else [frames[0].timestamp_seconds],
             "uncertainty": "This is a synthetic test response, not visual recognition."}
        ], limitations=["synthetic test"])


@pytest.fixture
def configured_client():
    provider = TestVisionProvider()
    app = create_app()
    settings = Settings(max_video_frames=4)
    app.dependency_overrides[get_provider] = lambda: provider
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        yield client, provider, settings


def upload(client, video=None, **data):
    return client.post("/api/video-flow", files={
        "video": ("clip.webm", SOURCE.read_bytes() if video is None else video, "video/webm")
    }, data=data)


def test_upload_decodes_real_frames_and_matches_evidence(configured_client):
    client, provider, settings = configured_client
    response = upload(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["analysis_mode"] == "live"
    assert body["expected_procedure_supplied"] is False
    assert len(body["frames"]) <= 4
    assert provider.seen_frames[0].image.data.startswith(b"\xff\xd8")
    assert base64.b64decode(body["frames"][0]["image_url"].split(",", 1)[1]) == provider.seen_frames[0].image.data
    assert body["actions"][0]["evidence_seconds"] == [body["frames"][0]["timestamp_seconds"]]
    assert body["sampled_seconds"][-1] > 22
    assert body["sample_interval_seconds"] > 7  # tail covered rather than truncated


def test_rejects_unseen_model_evidence(configured_client):
    client, provider, _ = configured_client
    provider.evidence = [0.1]  # valid video time, but no supplied frame exists here
    response = upload(client)
    assert response.status_code == 502
    assert "not sampled" in response.json()["detail"]


def test_upload_limits_and_invalid_files_never_reach_provider(configured_client):
    client, provider, settings = configured_client
    assert upload(client, b"").status_code == 400
    assert upload(client, b"not a video").status_code == 422
    settings.max_video_bytes = 5
    assert upload(client, b"sixsix").status_code == 413
    assert provider.seen_frames == []


def test_duration_limit_and_bad_interval(configured_client):
    client, provider, settings = configured_client
    settings.max_video_seconds = 2
    assert upload(client).status_code == 413
    for interval in [0, -1, "nan", "inf"]:
        assert upload(client, b"x", sample_interval_seconds=interval).status_code == 422
    assert provider.seen_frames == []


def test_default_mock_reports_unavailable_instead_of_fake_recognition():
    with TestClient(create_app()) as client:
        status = client.get("/api/video-flow/status").json()
        assert status["ready"] is False
        assert upload(client, b"x").status_code == 503


def test_missing_decoder_is_a_controlled_error(configured_client):
    client, _, _ = configured_client
    with patch("app.infrastructure.video.decoder_ready", return_value=False):
        assert upload(client).status_code == 503


def test_recorded_demo_has_seven_actions_real_frames_and_seekable_source():
    with TestClient(create_app()) as client:
        response = client.get("/api/video-flow/demo")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["analysis_mode"] == "recorded_demo"
        assert len(body["actions"]) == 7
        assert "door handle" in body["actions"][5]["label"]
        assert all(base64.b64decode(frame["image_url"].split(",", 1)[1]).startswith(b"\xff\xd8") for frame in body["frames"])
        assert body["transitions"][0]["from"] == 1
        for action in body["actions"]:
            assert set(action["evidence_seconds"]) <= set(body["sampled_seconds"])
        source = client.get("/api/video-flow/demo/video", headers={"Range": "bytes=0-99"})
        assert source.status_code == 206
        assert len(source.content) == 100


def test_demo_rejects_source_mismatch_before_decoding(tmp_path):
    (tmp_path / "source.webm").write_bytes(b"other source")
    (tmp_path / "detected-flow.json").write_text('{"source_sha256":"wrong"}', encoding="utf-8")
    video_routes.load_demo.cache_clear()
    try:
        with patch.object(video_routes, "DEMO_ASSETS", tmp_path), patch.object(video_routes, "read_video_frame") as decode:
            with TestClient(create_app()) as client:
                assert client.get("/api/video-flow/demo").status_code == 502
            decode.assert_not_called()
    finally:
        video_routes.load_demo.cache_clear()


def test_inference_failure_is_a_controlled_error(configured_client):
    client, provider, _ = configured_client
    async def fail(frames, duration):
        raise FlowInferenceError("Synthetic transport error")
    provider.discover_flow = fail
    assert upload(client).status_code == 502
