# Writing a provider

A provider turns `(steps, images)` into one verdict per step. To add a model backend you
implement one method and register it — nothing else in the system changes.

## Minimal example

```python
# stepcheck_providers/my_provider.py
from stepcheck_providers.base import VisionProvider
from stepcheck_providers.registry import register_provider
from stepcheck_providers.types import StepStatus, StepVerdict, VerificationInput


@register_provider("my-model")
class MyProvider(VisionProvider):
    def __init__(self, api_key: str | None = None, model: str = "my-model-v1"):
        self._api_key = api_key
        self._model = model

    async def verify(self, request: VerificationInput) -> list[StepVerdict]:
        # 1. Feed request.images + request.steps to your model.
        # 2. Return exactly one StepVerdict per step, keyed by step.index.
        return [
            StepVerdict(
                index=step.index,
                status=StepStatus.UNKNOWN,
                confidence=0.0,
                reason="not implemented",
            )
            for step in request.steps
        ]
```

Import the module (add it to `stepcheck_providers/__init__.py`) and select it with
`STEPCHECK_PROVIDER=my-model`.

## The contract

| Type | Purpose |
| --- | --- |
| `ProcedureStep(index, text)` | One 1-based instruction to verify |
| `ImagePayload(data, media_type)` | One image as raw bytes + MIME type |
| `VerificationInput(steps, images, context)` | Everything the provider receives |
| `StepVerdict(index, status, confidence, reason, evidence)` | The judgement for one step |
| `StepStatus` | `COMPLETED` ✅ / `NOT_DONE` ❌ / `UNKNOWN` ⚠️ |

Rules a provider must follow:

- Return **one verdict per step** (the application fills any gaps with `UNKNOWN`, but a
  good provider does not rely on that).
- `confidence` is in `[0, 1]`; the value object enforces this.
- Prefer `UNKNOWN` over guessing — undetermined is a first-class outcome.

## How this maps to the future roadmap

Video-flow discovery is an optional capability. Set `supports_flow = True` and
implement `discover_flow(frames: list[VideoFrame], duration_seconds: float) -> Detection`
using the contracts in `stepcheck_providers.flow`. No expected steps are provided.
Return actions with supporting timestamps, visible reasons, uncertainties, and
limitations. The shared validator rejects evidence from frames that were not supplied
and preserves ambiguous order when sightings overlap. OpenAI implements this through
image input and structured output; mock and existing image-only providers remain
unsupported instead of inventing video observations.

The contract was chosen so the roadmap items need **no application changes**:

| Future capability | How the contract already supports it |
| --- | --- |
| **JEPA / representation models** | A provider is free to embed images and steps and score similarity instead of prompting a VLM. The interface only asks for verdicts. |
| **Video input** | Already supported upstream through timestamped `VideoFrame`s and the optional `discover_flow` capability; video-native temporal inputs can extend this contract. |
| **Multiple images** | Already supported — `VerificationInput.images` is a list. |
| **PDF procedures** | Parse the PDF to Markdown before the use case; the provider is unaffected. |
| **Audio narration** | Add an optional `audio` field to `VerificationInput`; providers that ignore it keep working. |
| **Batch processing** | Providers are plain async objects — call `verify` concurrently over many inputs; no per-request web state. |

Because the boundary is data, not a specific model's API, each of these is an additive
change, not a rewrite.
