# Architecture

StepCheck AI is designed so the **model that understands the images is a replaceable
detail**, not the center of the system. Everything above the provider boundary works the
same whether the images are judged by a VLM today or a JEPA/video model tomorrow.

## Layers

```
┌─────────────────────────────────────────────────────────────┐
│ frontend/  Next.js UI — procedure editor, image upload,      │
│            per-step results                                  │
└───────────────┬─────────────────────────────────────────────┘
                │ HTTP (multipart: markdown + images)
┌───────────────▼─────────────────────────────────────────────┐
│ backend/ (FastAPI, clean architecture)                       │
│                                                              │
│   api/          routes + pydantic schemas (interface)        │
│   application/  VerifyProcedureUseCase, markdown parser      │
│   domain/       Procedure, StepResult, VerificationReport    │
│        │                                                     │
│        │ depends on the VisionProvider *abstraction* only    │
└────────┼─────────────────────────────────────────────────────┘
         │ (dependency inversion)
┌────────▼─────────────────────────────────────────────────────┐
│ providers/  stepcheck_providers — the model-agnostic contract│
│   VisionProvider (ABC)                                        │
│   VerificationInput / StepVerdict / StepStatus  (DTOs)        │
│   MockProvider · OpenAIProvider · <your model here>          │
└──────────────────────────────────────────────────────────────┘
```

## Why the provider package is separate

The `providers/` package (`stepcheck_providers`) is a standalone, independently testable
Python distribution. It contains **only** the contract types and the model
implementations — no web framework, no application logic. This does three things:

1. **Dependency inversion** — the application depends on the `VisionProvider` ABC, not on
   any concrete model. Concrete models are the low-level, swappable detail.
2. **Shared kernel** — the DTOs (`ProcedureStep`, `StepVerdict`, `StepStatus`) are the
   single source of truth for what a "verdict" is, reused by the domain layer instead of
   being redefined.
3. **Reusability** — the package can be pip-installed and used outside the web app (batch
   jobs, notebooks, other services).

## Request flow

1. The UI posts the Markdown procedure and one or more images to `POST /api/verify`.
2. `VerifyProcedureUseCase` parses the Markdown into a `Procedure` (ordered steps).
3. It calls `provider.verify(VerificationInput(steps, images))`.
4. The provider returns one `StepVerdict` per step (status, confidence, reason).
5. The use case assembles a `VerificationReport` with summary counts and returns it.

The provider never sees HTTP, and the API never sees a model SDK. The only thing crossing
the boundary is data.

## Single-video flow discovery

`POST /api/video-flow` writes the bounded upload to a temporary file. The FFmpeg
adapter in `infrastructure/video.py` extracts timestamped JPEG frames across the
whole video. `DiscoverFlowUseCase` calls `provider.discover_flow(frames, duration)`
without a procedure, then validates the observed evidence times and computes order.
It returns actions, reasons, uncertainties, transitions, and actual supporting images.
The temporary upload is removed after the request.

`stepcheck_providers.flow` owns the `VideoFrame` and `Detection` contracts and shared
`build_flow` validator, also reused by the MCP scripts. `VisionProvider.supports_flow`
defaults to false so existing image providers remain compatible; OpenAI implements
the optional capability. The mock provider never claims to recognize video.

The web UI seeks a local video when an action is selected and displays its decoded
evidence images. `/api/video-flow/demo` is a separately labeled replay of the saved
Codex review, source-hash checked against the bundled video. It performs no inference.

## Extension points

See [`providers.md`](./providers.md) for how the design accommodates JEPA, video models,
multiple images, PDF procedures, audio narration and batch processing without touching the
application layer.
