# Contributing to StepCheck AI

Thanks for your interest! This guide gets you productive quickly.

## Development setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e "./providers[openai,dev]" -e "./backend[dev]"
cd frontend && npm install
```

## Running the tests

```bash
cd providers && python -m pytest -q
cd backend   && python -m pytest -q
cd frontend  && npm run typecheck && npm run lint && npm run build
```

All of the above run in CI (`.github/workflows/ci.yml`) on every pull request.

## Adding a provider (the most valuable contribution)

1. Create `providers/stepcheck_providers/<name>_provider.py`.
2. Subclass `VisionProvider`, implement `async def verify(...)`, decorate with
   `@register_provider("<name>")`. See [`docs/providers.md`](docs/providers.md).
3. Import it in `providers/stepcheck_providers/__init__.py`.
4. Add a unit test under `providers/tests/`.

Keep heavy or optional SDK imports **lazy** (inside methods) and declare them as an
`optional-dependencies` extra in `providers/pyproject.toml`, so the core stays lightweight
and the test suite runs without credentials.

## Guidelines

- Match the existing style; keep the application layer free of model-specific code.
- Add or update tests for behavior changes.
- Prefer `UNKNOWN` over guessing in providers — undetermined is a valid answer.
- Conventional, descriptive commit messages are appreciated.

## Reporting issues

Open a GitHub issue with steps to reproduce, expected vs. actual behavior, and your
provider/config. Security issues: please disclose privately first.
