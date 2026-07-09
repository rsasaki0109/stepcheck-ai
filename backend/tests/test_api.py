import io

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_providers_lists_mock(client):
    response = client.get("/api/providers")
    assert response.status_code == 200
    body = response.json()
    assert body["active"] == "mock"
    assert "mock" in body["available"]


def test_verify_end_to_end_with_mock(client):
    files = [("images", ("photo.png", io.BytesIO(b"fake-image-bytes"), "image/png"))]
    data = {"procedure": "# Build\n1. step one\n2. step two"}
    response = client.post("/api/verify", data=data, files=files)

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert body["procedure_title"] == "Build"
    assert body["summary"]["total"] == 2
    assert len(body["steps"]) == 2
    assert body["steps"][0]["status"] in {"completed", "not_done", "unknown"}
    assert body["steps"][0]["symbol"] in {"✅", "❌", "⚠️"}


def test_verify_rejects_empty_procedure(client):
    files = [("images", ("photo.png", io.BytesIO(b"data"), "image/png"))]
    data = {"procedure": "no steps here"}
    response = client.post("/api/verify", data=data, files=files)
    assert response.status_code == 422


def test_verify_requires_image(client):
    # Sending an empty file should be treated as "no usable image".
    files = [("images", ("empty.png", io.BytesIO(b""), "image/png"))]
    data = {"procedure": "1. step"}
    response = client.post("/api/verify", data=data, files=files)
    assert response.status_code == 400
