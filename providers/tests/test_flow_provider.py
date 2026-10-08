"""OpenAI request contract tests; network responses are synthetic, not accuracy tests."""

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from stepcheck_providers import ImagePayload, create_provider
from stepcheck_providers.flow import Detection, FlowInferenceError, FlowUnavailableError, VideoFrame


def frames():
    return [VideoFrame(0.0, ImagePayload(b"first", "image/jpeg")),
            VideoFrame(0.75, ImagePayload(b"second", "image/jpeg"))]


async def test_openai_receives_timestamped_images_and_structured_schema():
    provider = create_provider("openai", api_key="test-key", model="test-model")
    detection = Detection(title="test", actions=[], limitations=["synthetic transport test"])
    parse = AsyncMock(return_value=SimpleNamespace(output_parsed=detection))
    provider._client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    assert await provider.discover_flow(frames(), 1.5) == detection
    kwargs = parse.call_args.kwargs
    assert kwargs["model"] == "test-model"
    assert kwargs["text_format"] is Detection
    assert kwargs["store"] is False
    content = kwargs["input"][0]["content"]
    images = [block for block in content if block["type"] == "input_image"]
    assert len(images) == 2
    assert base64.b64decode(images[0]["image_url"].split(",", 1)[1]) == b"first"
    assert content[1]["text"] == "Frame timestamp: 0 seconds"
    assert "without an expected procedure" in content[0]["text"]


async def test_missing_credentials_and_mock_cannot_generate_a_flow():
    provider = create_provider("mock")
    assert not provider.supports_flow
    with pytest.raises(FlowUnavailableError):
        await provider.discover_flow(frames(), 1.5)
    provider = create_provider("openai")
    provider._api_key = None
    with pytest.raises(FlowUnavailableError):
        await provider.discover_flow(frames(), 1.5)


@pytest.mark.parametrize("output", [None, RuntimeError("transport failure")])
async def test_failure_or_refusal_never_becomes_a_successful_flow(output):
    provider = create_provider("openai", api_key="test-key")
    parse = AsyncMock(side_effect=output) if isinstance(output, Exception) else AsyncMock(return_value=SimpleNamespace(output_parsed=output))
    provider._client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    with pytest.raises(FlowInferenceError):
        await provider.discover_flow(frames(), 1.5)
