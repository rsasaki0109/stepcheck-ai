"""Local model transport/parser tests; no model weights or accuracy simulation."""

import json
from unittest.mock import Mock

import pytest

from stepcheck_providers import ImagePayload, create_provider
from stepcheck_providers.flow import FlowInferenceError, VideoFrame
from stepcheck_providers.qwen_local_provider import parse_local_detection


def frames():
    return [VideoFrame(0, ImagePayload(b"first")), VideoFrame(1.234567, ImagePayload(b"second"))]


def response(ids=None):
    return json.dumps({"title": "test", "actions": [{"label": "visible action", "reason": "test response",
        "evidence_frame_ids": [0, 1] if ids is None else ids, "uncertainty": "synthetic parser test"}],
        "limitations": ["synthetic response"]})


def test_frame_ids_map_to_exact_decoded_timestamps():
    result = parse_local_detection("```json\n" + response([1]) + "\n```", frames())
    assert result.actions[0].evidence_seconds == [1.234567]


@pytest.mark.parametrize("ids", [[-1], [2], [999], [True], [0.5], ["1"], []])
def test_unsupported_evidence_never_gets_clamped_or_invented(ids):
    with pytest.raises(FlowInferenceError):
        parse_local_detection(response(ids), frames())


def test_malformed_output_never_becomes_a_flow():
    with pytest.raises(FlowInferenceError):
        parse_local_detection("I cannot identify the video.", frames())


async def test_local_request_has_actual_images_and_no_procedure():
    provider = create_provider("qwen-local")
    provider._generate = Mock(return_value=response())
    result = await provider.discover_flow(frames(), 2)
    images, prompt = provider._generate.call_args.args
    assert images[0].data == b"first"
    assert "frame_id 1 at 1.23457s" in prompt
    assert "No expected procedure" in prompt
    assert result.actions[0].evidence_seconds == [0, 1.234567]
    assert provider.supports_flow


async def test_frame_budget_prevents_unbounded_gpu_requests():
    provider = create_provider("qwen-local")
    provider._generate = Mock()
    with pytest.raises(FlowInferenceError):
        await provider.discover_flow(frames() * 17, 2)
    provider._generate.assert_not_called()
