# stepcheck-providers

Model-agnostic vision provider contracts for [StepCheck AI](../README.md).

This package defines the boundary between the application and any image-understanding
model. A provider takes a set of procedure steps plus one or more images and returns a
verdict per step. Swapping the underlying model — VLM today, JEPA or a video model
tomorrow — means adding a new class here; nothing in the application changes.

```python
from stepcheck_providers import create_provider, VerificationInput, ProcedureStep, ImagePayload

provider = create_provider("mock")
verdicts = await provider.verify(
    VerificationInput(
        steps=[ProcedureStep(index=1, text="Install the motherboard")],
        images=[ImagePayload(data=b"...", media_type="image/png")],
    )
)
```

See [`../docs/providers.md`](../docs/providers.md) for how to implement your own.

Open-ended video flow detection uses the optional `supports_flow` / `discover_flow`
capability. `stepcheck_providers.flow` contains timestamped `VideoFrame`s, the structured
`Detection` output, and the evidence/order validator shared by the web API and MCP.
OpenAI supports detection; mock supports only image-procedure verification.
