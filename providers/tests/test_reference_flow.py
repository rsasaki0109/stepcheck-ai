"""Reference contract/parser/transport tests; synthetic replies do not measure vision accuracy."""

import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from stepcheck_providers import ImagePayload, create_provider
from stepcheck_providers.flow import FlowInferenceError, FlowUnavailableError, VideoFrame
from stepcheck_providers.reference_flow import ReferenceFlow, ReferenceJudgment, build_reference_flow
from stepcheck_providers.qwen_local_provider import parse_local_reference

REF = ReferenceFlow(title="Fixture", steps=[{"id": "a", "label": "A", "criterion": "Visible contact"},
    {"id": "b", "label": "B", "criterion": "Visible operation"}])
FRAMES = [VideoFrame(0, ImagePayload(b"first", "image/jpeg")),
    VideoFrame(1.234567, ImagePayload(b"second", "image/jpeg"))]


def observation(step, times, status="observed"):
    return {"step_id": step, "status": status, "reason": "Synthetic fixture, not vision recognition",
        "evidence_seconds": times, "uncertainty": "Fixture only"}


def build(items):
    return build_reference_flow(REF, ReferenceJudgment(observations=items), [0, 1.234567], 2)


def test_sample_order_comes_from_citations_and_unknown_is_preserved():
    forward = build([observation("b", [1.234567]), observation("a", [0])])
    assert forward["order_status"] == "supported_sample_order"
    assert [s["step_id"] for s in forward["steps"]] == ["a", "b"]
    assert build([observation("a", [1.234567]), observation("b", [0])])["order_status"] == "violated"
    assert build([observation("a", [0]), observation("b", [0])])["order_status"] == "unknown"
    missing = build([observation("a", [0]), observation("b", [], "unknown")])
    assert missing["order_status"] == "unknown"
    assert missing["steps"][1]["status"] == "unknown"
    assert missing["steps"][1]["evidence_seconds"] == []
    assert "confidence" not in missing["steps"][0]


@pytest.mark.parametrize("items", [
    [observation("a", [0])], [observation("a", [0]), observation("a", [1.234567])],
    [observation("a", [0]), observation("invented", [1.234567])],
    [observation("a", []), observation("b", [1.234567])],
    [observation("a", [0.1]), observation("b", [1.234567])],
    [observation("a", [0]), observation("b", [1.23457])],
])
def test_invented_missing_and_unsupplied_evidence_are_errors(items):
    with pytest.raises(ValueError):
        build(items)


@pytest.mark.parametrize("change", [{"status": "not_done"}, {"evidence_seconds": [float("nan")]},
    {"evidence_seconds": [False]}, {"evidence_seconds": ["0"]}, {"reason": " "}])
def test_invalid_model_claims_are_not_coerced(change):
    with pytest.raises(ValidationError):
        ReferenceJudgment(observations=[{**observation("a", [0]), **change}])


def test_reference_ids_must_be_unique_and_nonempty():
    with pytest.raises(ValidationError):
        ReferenceFlow(title="Fixture", steps=[{"id": "a", "label": "A"}, {"id": "a", "label": "B"}])
    with pytest.raises(ValidationError):
        ReferenceFlow(title="Fixture", steps=[{"id": " ", "label": "A"}])


async def test_openai_receives_given_criteria_real_images_and_exact_times():
    provider = create_provider("openai", api_key="synthetic", model="test-model")
    result = ReferenceJudgment(observations=[observation("a", [0]), observation("b", [], "unknown")])
    parse = AsyncMock(return_value=SimpleNamespace(output_parsed=result))
    provider._client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    assert await provider.verify_reference_flow(REF, FRAMES, 2) == result
    kwargs = parse.call_args.kwargs
    assert kwargs["text_format"] is ReferenceJudgment and kwargs["store"] is False
    blocks = kwargs["input"][0]["content"]
    assert '"criterion": "Visible operation"' in blocks[0]["text"]
    assert "not_done" in blocks[0]["text"] and "unknown" in blocks[0]["text"]
    assert blocks[3]["text"] == "Frame timestamp: 1.234567 seconds"
    assert base64.b64decode(blocks[2]["image_url"].split(",", 1)[1]) == b"first"


@pytest.mark.parametrize("output", [None, RuntimeError("transport error")])
async def test_openai_refusal_or_transport_failure_is_not_a_verdict(output):
    provider = create_provider("openai", api_key="synthetic")
    parse = AsyncMock(side_effect=output) if isinstance(output, Exception) else AsyncMock(return_value=SimpleNamespace(output_parsed=output))
    provider._client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    with pytest.raises(FlowInferenceError):
        await provider.verify_reference_flow(REF, FRAMES, 2)


async def test_mock_and_missing_credentials_cannot_review_a_reference():
    for provider in (create_provider("mock"), create_provider("openai")):
        if provider.name == "openai":
            provider._api_key = None
        with pytest.raises(FlowUnavailableError):
            await provider.verify_reference_flow(REF, FRAMES, 2)


def local_response(ids):
    return json.dumps({"observations": [{"step_id": "b", "status": "unknown", "reason": "fixture",
        "evidence_frame_ids": ids, "uncertainty": "fixture only"}]})


@pytest.mark.parametrize("ids", [[-1], [2], [True], [0.5], ["1"]])
def test_local_unsupplied_or_coerced_frame_ids_are_rejected(ids):
    with pytest.raises(FlowInferenceError):
        parse_local_reference(local_response(ids), FRAMES)


async def test_local_given_reference_uses_actual_images_and_exact_id_mapping():
    provider = create_provider("qwen-local", framewise=True)
    provider._generate = Mock(return_value=local_response([1]))
    result = await provider.verify_reference_flow(REF, FRAMES, 2)
    images, prompt, labels = provider._generate.call_args.args
    assert images[0].data == b"first"
    assert "Visible operation" in prompt and "evidence_frame_ids" in prompt
    assert labels[1].startswith("frame_id 1 at 1.234567s")
    assert result.observations[0].status == "unknown"
    assert result.observations[0].evidence_seconds == [1.234567]
    with pytest.raises(FlowInferenceError):
        await provider.verify_reference_flow(REF, FRAMES * 13, 2)
    assert provider._generate.call_count == 1
