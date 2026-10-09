"""Actual upload/FFmpeg follow-up tests with explicitly synthetic vision replies."""

import asyncio
import hashlib
import json
from pathlib import Path
import shutil
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from app.api.dependencies import get_provider
from app.config import Settings, get_settings
from app.main import create_app
from app.application.verify_video_flow_use_case import VerifyVideoFlowUseCase
from app.infrastructure.video import sample_video, VideoDecodeError
from stepcheck_providers import VisionProvider
from stepcheck_providers.flow import FlowInferenceError
from stepcheck_providers.reference_flow import ReferenceFlow, ReferenceJudgment

SOURCE = Path(__file__).resolve().parents[2] / "docs/assets/video-demo/new-video-transfer/source.webm"
REF = {"title": "Synthetic auto-flow fixture", "steps": [
    {"id": "a", "label": "Left anchor"}, {"id": "b", "label": "Unknown target"}, {"id": "c", "label": "Right anchor"}]}


def observation(step, times, status="observed"):
    return {"step_id": step, "status": status, "reason": "Synthetic transport fixture; not visual recognition",
        "evidence_seconds": times, "uncertainty": "Fixture only"}


class AutoFixture(VisionProvider):
    name = "synthetic-auto-fixture"
    supports_reference_flow = True
    def __init__(self):
        self.requests = []
        self.mode = "found"
        self.mutate = None
    async def verify(self, request):
        return []
    async def verify_reference_flow(self, reference, frames, duration):
        self.requests.append((reference, frames, duration))
        if len(self.requests) == 1:
            if self.mutate:
                self.mutate.write_bytes(b"changed source")
            left, right = frames[0].timestamp_seconds, frames[-1].timestamp_seconds
            if self.mode == "reverse":
                left, right = right, left
            target = observation("b", [frames[1].timestamp_seconds]) if self.mode in ("known", "reverse") else observation(
                "b", [frames[1].timestamp_seconds] if self.mode == "budget_exhausted" else [], "unknown")
            items = [observation("a", [left]), target, observation("c", [right])]
        else:
            if self.mode == "error":
                raise FlowInferenceError("Synthetic second-pass transport error")
            old = {f.timestamp_seconds for f in self.requests[0][1]}
            timestamp = next(f.timestamp_seconds for f in frames if f.timestamp_seconds not in old)
            items = [observation("b", [] if self.mode == "unknown" else [timestamp],
                "unknown" if self.mode == "unknown" else "observed")]
            if self.mode == "old_citation":
                items = [observation("b", [self.requests[0][1][1].timestamp_seconds])]
            if self.mode == "changes_known":
                items.append(observation("a", [timestamp]))
        return ReferenceJudgment(observations=items)


@pytest.fixture
def configured():
    provider, settings = AutoFixture(), Settings(max_video_frames=4)
    app = create_app()
    app.dependency_overrides[get_provider] = lambda: provider
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        yield client, provider, settings


def upload(client, **data):
    return client.post("/api/video-flow/verify", files={"video": ("clip.webm", SOURCE.read_bytes(), "video/webm")},
        data={"reference_json": json.dumps(REF), "sample_interval_seconds": "20", "auto_refine": "true", **data})


def test_two_real_image_passes_budget_fit_and_preserved_known_judgments(configured):
    client, provider, _ = configured
    response = upload(client)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["workflow"]["sampling_requests"] == 2
    assert result["workflow"]["stop_reason"] == "no_unknown_steps"
    assert result["workflow"]["max_frames"] == 4
    assert result["order_status"] == "supported_sample_order"
    assert result["initial"]["order_status"] == "unknown"
    assert result["initial"]["sampled_seconds"] == [0, 20, 31.936]
    assert result["workflow"]["interval_selection"]["chosen_interval_seconds"] == 16
    assert result["refinement"]["added_seconds"] == [16]
    assert result["sample_interval_seconds"] is None
    assert result["sampled_seconds"] == [0, 16, 20, 31.936]
    assert [s.id for s in provider.requests[1][0].steps] == ["b"]
    assert provider.requests[1][1][0] is provider.requests[0][1][0]
    assert provider.requests[1][1][-1] is provider.requests[0][1][-1]
    assert all(f.image.data.startswith(b"\xff\xd8") for f in provider.requests[1][1])
    assert result["steps"][0] == result["initial"]["steps"][0]
    assert result["steps"][2] == result["initial"]["steps"][2]


def test_unknown_after_followup_stops_after_two_judgments(configured):
    client, provider, _ = configured
    provider.mode = "unknown"
    result = upload(client).json()
    assert result["workflow"]["sampling_requests"] == 2
    assert result["workflow"]["stop_reason"] == "unknown_after_followup"
    assert result["workflow"]["unknown_step_ids"] == ["b"]
    assert result["steps"][1]["status"] == "unknown" and result["order_status"] == "unknown"
    assert len(provider.requests) == 2


@pytest.mark.parametrize("mode,order", [("known", "supported_sample_order"), ("reverse", "violated")])
def test_no_unknown_skips_followup_and_retains_order_violations(configured, mode, order):
    client, provider, _ = configured
    provider.mode = mode
    result = upload(client).json()
    assert result["order_status"] == order
    assert result["workflow"]["sampling_requests"] == 1
    assert result["workflow"]["stop_reason"] == "no_unknown_steps"
    assert len(provider.requests) == 1 and result["refinement"] is None


@pytest.mark.parametrize("mode,stop", [("found", "no_new_samples"), ("budget_exhausted", "refinement_budget_exhausted")])
def test_no_new_or_over_budget_preserves_initial_unknown_and_does_not_infer(configured, mode, stop):
    client, provider, _ = configured
    provider.mode = mode
    result = upload(client, refinement_max_frames=2).json()
    assert result["workflow"]["stop_reason"] == stop
    assert result["steps"] == result["initial"]["steps"]
    assert result["order_status"] == "unknown" and len(provider.requests) == 1


@pytest.mark.parametrize("mode", ["old_citation", "changes_known", "error"])
def test_invalid_second_response_never_returns_partial_success(configured, mode):
    client, provider, _ = configured
    provider.mode = mode
    result = upload(client)
    assert result.status_code == 502
    assert "steps" not in result.json() and len(provider.requests) == 2


def test_provider_budget_caps_followup_and_invalid_options_do_not_infer(configured):
    client, provider, _ = configured
    for data in ({"refinement_max_frames": 1}, {"refinement_max_frames": 97},
                 {"refinement_interval_seconds": "nan"}, {"refinement_interval_seconds": 0}):
        assert upload(client, **data).status_code == 422
    assert provider.requests == []
    provider.max_flow_frames = 3
    result = upload(client, refinement_max_frames=96).json()
    assert result["workflow"]["max_frames"] == 3
    assert len(provider.requests[1][1]) <= 3


def test_new_frame_decode_failure_is_an_error_after_initial_review(configured):
    client, provider, _ = configured
    with patch("app.application.verify_video_flow_use_case.read_video_frame", side_effect=VideoDecodeError("Fixture decode failure")):
        result = upload(client)
    assert result.status_code == 422 and "steps" not in result.json()
    assert len(provider.requests) == 1


def test_changed_video_is_rejected_before_any_followup_decode(tmp_path):
    video = tmp_path / "video.webm"
    shutil.copyfile(SOURCE, video)
    sampled = sample_video(video, 20, 120, 4)
    provider = AutoFixture()
    provider.mutate = video
    with patch("app.application.verify_video_flow_use_case.read_video_frame") as decode:
        with pytest.raises(FlowInferenceError, match="changed"):
            asyncio.run(VerifyVideoFlowUseCase(provider, "fixture").execute(ReferenceFlow.model_validate(REF),
                sampled, hashlib.sha256(SOURCE.read_bytes()).hexdigest(), video=video, auto_refine=True))
        decode.assert_not_called()
    assert len(provider.requests) == 1
