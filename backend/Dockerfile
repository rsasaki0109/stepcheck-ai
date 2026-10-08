# StepCheck AI backend image.
# Build context is the repository root so the sibling `providers/` package is available:
#   docker build -f backend/Dockerfile -t stepcheck-backend .
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install the provider package first (its own dependency layer).
COPY providers /app/providers
RUN pip install --no-cache-dir "./providers[openai]"

# Then the backend.
COPY backend /app/backend
RUN pip install --no-cache-dir ./backend

COPY docs/assets/video-demo/source.webm docs/assets/video-demo/detected-flow.json /app/docs/assets/video-demo/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app/backend"]
