<div align="center">

# StepCheck AI

**Turn work images into a step-by-step check.**

Markdown procedure + work images → verdicts, confidence, and reasons.

[Quick start](#quick-start) · [How it works](#how-it-works) · [Architecture](docs/architecture.md) · [Build a provider](docs/providers.md)

![StepCheck AI animated workflow: write a Markdown procedure, attach a work image, and review per-step verdicts](docs/assets/demo.gif)

<sub>Illustrated workflow using the included mock provider. Mock verdicts are deterministic; image contents are not analyzed.</sub>

</div>

StepCheck AI checks whether work was carried out **according to a written procedure** by
looking at photos of the work. You provide a procedure in Markdown and one or more images;
StepCheck judges each step as ✅ completed, ❌ not done, or ⚠️ undetermined — with a
confidence score and a human-readable reason.

The image model sits behind a model-agnostic `VisionProvider` interface. Add and register
a provider to change the model without rewriting the use case or UI.

## How it works

1. **Write the procedure.** Paste a Markdown ordered list, bullet list, or checklist.
2. **Attach work images.** Add one or more photos of the work.
3. **Run the check.** Review each step's verdict, confidence, and reason.

Try the [PC assembly](examples/pc-build.md) or [coffee brewing](examples/coffee-brewing.md)
procedure. The default `mock` provider exercises the workflow without an API key;
select `openai` for image analysis.

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

Runs with the keyless `mock` provider by default. To use OpenAI, create a `.env` file
at the repository root:

```dotenv
STEPCHECK_PROVIDER=openai
STEPCHECK_MODEL=gpt-4o
OPENAI_API_KEY=your-api-key
```

Then run `docker compose up --build` again. The `.env` file is ignored by Git.

### Option B — Run locally

Run the backend and frontend in separate terminals, starting at the repository root.

**Backend** (Python 3.10+, macOS / Linux):

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e "./providers[openai,dev]" -e "./backend[dev]"
cd backend
uvicorn app.main:app --reload --port 8000
```

<details>
<summary>Backend — Windows PowerShell</summary>

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "./providers[openai,dev]" -e "./backend[dev]"
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

</details>

**Frontend** (Node 20+):

```bash
cd frontend
npm install
npm run dev      # http://localhost:3000
```

The frontend connects to `http://localhost:8000` by default. To change it, copy
[`frontend/.env.local.example`](frontend/.env.local.example) to `frontend/.env.local`
and set `NEXT_PUBLIC_API_BASE`.

### Try it from the API

On macOS / Linux:

```bash
curl -X POST http://localhost:8000/api/verify \
  -F "procedure=<examples/pc-build.md" \
  -F "images=@photo.jpg"
```

---

## Configuration

Backend settings are environment variables (see [`backend/.env.example`](backend/.env.example)).
For local development, place them in `backend/.env`; Compose reads the `.env` at the repository root.

| Variable | Default | Description |
| --- | --- | --- |
| `STEPCHECK_PROVIDER` | `mock` | Provider name (`mock`, `openai`, …) |
| `STEPCHECK_MODEL` | `gpt-4o` | Model id passed to the provider |
| `OPENAI_API_KEY` | — | Required when provider is `openai` |
| `STEPCHECK_MAX_IMAGES` | `8` | Max images per request |
| `STEPCHECK_MAX_IMAGE_BYTES` | `10485760` | Max bytes per image (10 MiB) |
| `STEPCHECK_CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed frontend origins, as a JSON array |

The supplied Compose file forwards the provider, model, and API key settings. Add other
settings to `services.backend.environment` when customizing limits or origins.

Frontend: `NEXT_PUBLIC_API_BASE` (default `http://localhost:8000`).

---

## README animation

The GIF is stored at [`docs/assets/demo.gif`](docs/assets/demo.gif). Embed it from the
repository root with:

```markdown
![StepCheck AI workflow](docs/assets/demo.gif)
```

To regenerate it with verdicts from the included `MockProvider`:

```bash
python -m pip install Pillow
python scripts/generate_readme_gif.py
```

The generator draws a workflow illustration with a schematic evidence image;
it is not a recording of the web UI. No running app or API key is needed.

---

## Testing

From the repository root, with development dependencies installed:

```bash
python -m pytest providers/tests -q      # contract + providers
python -m pytest backend/tests -q        # parser, use case, API
cd frontend
npm run typecheck
npm run lint
npm run build
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
