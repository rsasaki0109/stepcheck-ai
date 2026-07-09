# StepCheck AI

> **AI-powered procedural verification from images.**

StepCheck AI checks whether work was carried out **according to a written procedure** by
looking at photos of the work. You provide a procedure in Markdown and one or more images;
StepCheck judges each step as ✅ completed, ❌ not done, or ⚠️ undetermined — with a
confidence score and a human-readable reason.

It is **not a VLM demo**. The model that understands the images sits behind a small,
model-agnostic `VisionProvider` boundary, so a VLM today can be swapped for a JEPA-style
representation model, a video model, or anything else — by adding a class, not by rewriting
the app.

---

## Features

- 📋 **Markdown procedures** — ordered lists, bullets, or checkboxes.
- 🖼️ **One or many images** per check.
- ✅❌⚠️ **Per-step verdicts** with confidence and an explanation of the reason.
- 🔌 **Pluggable providers** — `mock` (no API key) and `openai` (GPT-4o) included; add your
  own in one file.
- 🧱 **Clean architecture** backend (domain / application / interface) with a shared
  contract package.
- 🐳 **Docker & Compose**, **typed** end to end, **unit-tested**, **CI** on GitHub Actions.

---

## Architecture

```
frontend/    Next.js + TypeScript + Tailwind UI
backend/     FastAPI, clean architecture (domain / application / api)
providers/   stepcheck_providers — model-agnostic VisionProvider contract + models
examples/    Sample procedures
docs/        Architecture & provider-authoring guides
```

The application depends only on the `VisionProvider` **abstraction**; concrete models are a
replaceable detail. See [`docs/architecture.md`](docs/architecture.md) and
[`docs/providers.md`](docs/providers.md).

```
UI ──HTTP(markdown + images)──▶ FastAPI ──▶ VerifyProcedureUseCase
                                                   │ depends on abstraction
                                                   ▼
                                        VisionProvider (ABC)
                                   MockProvider · OpenAIProvider · …
```

---

## Quick Start

### Option A — Docker Compose (full stack)

```bash
git clone https://github.com/rsasaki0109/stepcheck-ai.git
cd stepcheck-ai
docker compose up --build
# Frontend: http://localhost:3000   API docs: http://localhost:8000/docs
```

Runs with the keyless `mock` provider by default. To use OpenAI:

```bash
STEPCHECK_PROVIDER=openai OPENAI_API_KEY=sk-... docker compose up --build
```

### Option B — Run locally

**Backend** (Python 3.10+):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e "./providers[openai,dev]" -e "./backend[dev]"
cd backend && uvicorn app.main:app --reload --port 8000
```

**Frontend** (Node 20+):

```bash
cd frontend
cp .env.local.example .env.local
npm install && npm run dev      # http://localhost:3000
```

### Try it from the API

```bash
curl -X POST http://localhost:8000/api/verify \
  -F "procedure=$(cat examples/pc-build.md)" \
  -F "images=@photo.jpg"
```

---

## Configuration

Backend settings are environment variables (see [`backend/.env.example`](backend/.env.example)):

| Variable | Default | Description |
| --- | --- | --- |
| `STEPCHECK_PROVIDER` | `mock` | Provider name (`mock`, `openai`, …) |
| `STEPCHECK_MODEL` | `gpt-4o` | Model id passed to the provider |
| `OPENAI_API_KEY` | — | Required when provider is `openai` |
| `STEPCHECK_MAX_IMAGES` | `8` | Max images per request |

Frontend: `NEXT_PUBLIC_API_BASE` (default `http://localhost:8000`).

---

## Screenshots

> _Placeholder — add screenshots/GIFs of the UI here._

| Input (procedure + images) | Results (per-step verdicts) |
| --- | --- |
| _`docs/screenshot-input.png`_ | _`docs/screenshot-results.png`_ |

---

## Testing

```bash
cd providers && python -m pytest -q      # contract + providers
cd backend   && python -m pytest -q      # parser, use case, API
cd frontend  && npm run typecheck && npm run lint && npm run build
```

---

## Roadmap

- [ ] JEPA / representation-model provider
- [ ] Video input (frame sampling) and video-native models
- [ ] PDF procedure ingestion
- [ ] Audio narration as an additional signal
- [ ] Batch processing API
- [ ] Per-step image/region evidence highlighting
- [ ] Gemini and Qwen2.5-VL providers

The contract is designed so these are **additive** — see [`docs/providers.md`](docs/providers.md).

---

## Contributing

Contributions are welcome! See [`CONTRIBUTING.md`](CONTRIBUTING.md). A great first
contribution is a new provider (Gemini, Qwen2.5-VL, a local model) — the interface is one
method.

---

## License

[MIT](LICENSE) © StepCheck AI contributors
