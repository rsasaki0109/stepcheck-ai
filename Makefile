.PHONY: help install backend frontend test test-backend test-providers lint compose-up compose-down

help:
	@echo "StepCheck AI — common tasks"
	@echo "  make install         Install providers + backend into the current Python env"
	@echo "  make backend         Run the FastAPI backend (http://localhost:8000)"
	@echo "  make frontend        Run the Next.js frontend (http://localhost:3000)"
	@echo "  make test            Run all Python tests"
	@echo "  make compose-up      Build and start the full stack with Docker Compose"

install:
	pip install -e "./providers[openai,dev]"
	pip install -e "./backend[dev]"

backend:
	cd backend && uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm install && npm run dev

test: test-providers test-backend

test-providers:
	cd providers && python -m pytest -q

test-backend:
	cd backend && python -m pytest -q

compose-up:
	docker compose up --build

compose-down:
	docker compose down
