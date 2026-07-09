"""OpenAI (GPT-4o family) vision provider.

The ``openai`` package is imported lazily so the rest of StepCheck works — and the
test suite runs — without it installed. Install with ``pip install stepcheck-providers[openai]``.
"""

from __future__ import annotations

import base64
import json
import os

from .base import VisionProvider
from .registry import register_provider
from .types import ProcedureStep, StepStatus, StepVerdict, VerificationInput

_SYSTEM_PROMPT = (
    "You are a meticulous quality-control inspector. You are given a numbered list of "
    "work-procedure steps and one or more photographs of the work. For EACH step, decide "
    "from the images whether it has been carried out.\n\n"
    "Return strict JSON of the form: "
    '{"results": [{"index": <int>, "status": "completed|not_done|unknown", '
    '"confidence": <float 0-1>, "reason": "<short justification>"}]}\n'
    "Rules:\n"
    "- 'completed' only when the images clearly show the step is done.\n"
    "- 'not_done' when the images clearly show it is not done.\n"
    "- 'unknown' when the images do not let you tell.\n"
    "- Provide one object per step, using the step's index.\n"
    "- Keep 'reason' to one or two sentences, grounded in what is visible."
)


@register_provider("openai")
class OpenAIProvider(VisionProvider):
    """Verifies steps using an OpenAI multimodal chat model."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o",
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._model = model
        self._base_url = base_url
        self._client = None  # created lazily

    async def health(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):  # noqa: ANN202 - external type imported lazily
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:  # pragma: no cover - import guard
                raise RuntimeError(
                    "The 'openai' package is required for OpenAIProvider. "
                    "Install it with: pip install stepcheck-providers[openai]"
                ) from exc
            self._client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client

    async def verify(self, request: VerificationInput) -> list[StepVerdict]:
        client = self._get_client()
        content: list[dict] = [{"type": "text", "text": _render_steps(request)}]
        for image in request.images:
            b64 = base64.b64encode(image.data).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{image.media_type};base64,{b64}"},
                }
            )

        response = await client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        raw = response.choices[0].message.content or "{}"
        return _parse_verdicts(raw, request.steps)


def _render_steps(request: VerificationInput) -> str:
    lines = ["Procedure steps to verify:"]
    if request.context:
        lines.append(f"Context: {request.context}")
    for step in request.steps:
        lines.append(f"{step.index}. {step.text}")
    return "\n".join(lines)


def _parse_verdicts(raw: str, steps: list[ProcedureStep]) -> list[StepVerdict]:
    """Parse the model's JSON, tolerating omissions by filling gaps with 'unknown'."""
    try:
        data = json.loads(raw)
        items = data.get("results", data if isinstance(data, list) else [])
    except (json.JSONDecodeError, AttributeError):
        items = []

    by_index: dict[int, StepVerdict] = {}
    for item in items:
        try:
            index = int(item["index"])
            status = StepStatus(str(item.get("status", "unknown")).lower())
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0.0))))
            reason = str(item.get("reason", "")).strip() or "No reason provided by the model."
        except (KeyError, ValueError, TypeError):
            continue
        by_index[index] = StepVerdict(index, status, confidence, reason)

    return [
        by_index.get(
            step.index,
            StepVerdict(
                step.index,
                StepStatus.UNKNOWN,
                0.0,
                "The model did not return a verdict for this step.",
            ),
        )
        for step in steps
    ]
