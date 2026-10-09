"""Capture a real, offline local-Qwen call through the Web upload API.

Run from the repository root using the cached Qwen3 environment. No predictions
are supplied or changed by this recorder. The adjacent manifest preserves errors.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import version

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "providers"), str(ROOT / "backend")]
REVISION = "ebb281ec70b05090aa6165b016eac8ec08e71b17"
CACHE = ROOT / ".tmp-flow-local/hf-qwen3"
os.environ.update(HF_HOME=str(CACHE), HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
MODEL_PATH = CACHE / "hub/models--Qwen--Qwen3-VL-4B-Instruct/snapshots" / REVISION

from fastapi.testclient import TestClient
from app.main import create_app
from app.api.dependencies import get_provider
from app.config import Settings, get_settings
from stepcheck_providers.qwen_local_provider import QwenLocalProvider
import torch


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


class Recorder(QwenLocalProvider):
    def _generate(self, images, prompt, frame_labels=None):
        folder = OUT / f"pass-{len(manifest['calls']) + 1:02d}"
        folder.mkdir()
        request = {"prompt": prompt, "frame_labels": frame_labels, "images": []}
        for index, image in enumerate(images):
            path = folder / f"frame-{index:02d}.jpg"
            path.write_bytes(image.data)
            request["images"].append({"file": path.name, "media_type": image.media_type,
                                      "sha256": sha(image.data)})
        write_json(folder / "request.json", request)
        item = {"directory": folder.name, "image_count": len(images), "status": "running"}
        manifest["calls"].append(item)
        write_json(OUT / "manifest.json", manifest)
        started = time.monotonic()
        print(f"Real GPU inference: {folder.name}, {len(images)} source images", flush=True)
        try:
            raw = super()._generate(images, prompt, frame_labels)
            (folder / "response.txt").write_text(raw, encoding="utf-8")
            item["status"] = "generated; application validation pending"
            return raw
        except Exception as exc:
            item.update(status="inference_error", error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            item["elapsed_seconds"] = round(time.monotonic() - started, 3)
            write_json(OUT / "manifest.json", manifest)
            print(f"Finished {folder.name}: {item['status']}, {item['elapsed_seconds']}s", flush=True)


if __name__ == "__main__":
    if (OUT / "manifest.json").exists():
        raise SystemExit("Capture already exists; preserve it and use a new directory for another run.")
    source = ROOT / "docs/assets/video-demo/new-video-transfer/source.webm"
    reference = ROOT / "examples/new-video-handwashing-flow.json"
    manifest = {"executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": "Qwen/Qwen3-VL-4B-Instruct", "model_revision": REVISION,
        "offline": True, "load_in_4bit": True, "keep_vision_fp16": True,
        "max_pixels": 256 * 28 * 28, "max_new_tokens": 2400,
        "gpu": torch.cuda.get_device_name(0),
        "packages": {name: version(name) for name in ("torch", "transformers", "accelerate", "bitsandbytes")},
        "source_sha256": sha(source.read_bytes()), "reference_sha256": sha(reference.read_bytes()),
        "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "endpoint": "POST /api/video-flow/verify via FastAPI TestClient; real multipart upload and GPU inference",
        "form": {"sample_interval_seconds": "2", "auto_refine": "true",
                 "refinement_interval_seconds": "0.25", "refinement_max_frames": "12"},
        "backend_max_video_frames": 12, "known_video": True,
        "accuracy_benchmark": False, "status": "running", "calls": [], "code_sha256": {}}
    paths = [Path(__file__).relative_to(ROOT),
        Path("providers/stepcheck_providers/qwen_local_provider.py"),
        Path("providers/stepcheck_providers/reference_flow.py"),
        Path("providers/stepcheck_providers/reference_refinement.py"),
        Path("backend/app/api/video_routes.py"),
        Path("backend/app/api/schemas.py"),
        Path("backend/app/application/verify_video_flow_use_case.py"),
        Path("backend/app/infrastructure/video.py")]
    for path in paths:
        data = (ROOT / path).read_bytes()
        manifest["code_sha256"][path.as_posix()] = sha(data)
        snapshot = OUT / "code" / path
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(data)
    write_json(OUT / "manifest.json", manifest)
    provider = Recorder(model=str(MODEL_PATH), load_in_4bit=True, keep_vision_fp16=True)
    app = create_app()
    app.dependency_overrides[get_provider] = lambda: provider
    app.dependency_overrides[get_settings] = lambda: Settings(max_video_frames=12)
    started = time.monotonic()
    with TestClient(app) as client, source.open("rb") as video:
        response = client.post("/api/video-flow/verify", files={"video": (source.name, video, "video/webm")},
            data={**manifest["form"], "reference_json": reference.read_text(encoding="utf-8")})
    result = response.json()
    write_json(OUT / "api-response.json", result)
    manifest.update(status="validated_response" if response.status_code == 200 else "api_error",
                    http_status=response.status_code, elapsed_seconds=round(time.monotonic() - started, 3))
    if response.status_code == 200:
        manifest.update(order_status=result["order_status"], workflow=result["workflow"])
    else:
        manifest["error"] = result
    manifest["files"] = {path.relative_to(OUT).as_posix(): sha(path.read_bytes())
                         for path in sorted(OUT.rglob("*")) if path.is_file() and path.name != "manifest.json"}
    write_json(OUT / "manifest.json", manifest)
    print(json.dumps({key: manifest[key] for key in ("status", "http_status", "elapsed_seconds", "calls")}), flush=True)
