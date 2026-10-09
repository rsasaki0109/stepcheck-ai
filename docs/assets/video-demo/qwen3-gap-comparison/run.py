"""Freeze a prior real Qwen initial answer; run ONE new real follow-up.

This is a known-video sampling comparison, not a fresh two-inference upload or
an accuracy benchmark. No expected timestamps enter the selector or model.
"""
import asyncio
import base64
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "providers"), str(ROOT / "backend")]
CACHE = ROOT / ".tmp-flow-local/hf-qwen3"
REVISION = "ebb281ec70b05090aa6165b016eac8ec08e71b17"
os.environ.update(HF_HOME=str(CACHE), HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
from stepcheck_providers.qwen_local_provider import QwenLocalProvider
from stepcheck_providers.reference_flow import ReferenceFlow, ReferenceJudgment
from app.application.verify_video_flow_use_case import VerifyVideoFlowUseCase
from app.infrastructure.video import SampledVideo, read_video_frame
import torch


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


class FrozenInitialThenQwen(QwenLocalProvider):
    reviews = 0

    async def verify_reference_flow(self, reference, frames, duration_seconds):
        self.reviews += 1
        if self.reviews == 1:
            assert reference.model_dump() == prior["reference"]
            assert duration_seconds == prior["duration_seconds"]
            assert [f.timestamp_seconds for f in frames] == prior["initial"]["sampled_seconds"]
            original_images = {f["timestamp_seconds"]: base64.b64decode(f["image_url"].split(",")[1])
                               for f in prior["frames"]}
            assert all(f.image.data == original_images[f.timestamp_seconds] for f in frames)
            return ReferenceJudgment(observations=[{key: s[key] for key in
                ("step_id", "status", "reason", "evidence_seconds", "uncertainty")} for s in prior["initial"]["steps"]])
        assert self.reviews == 2, "Only one new GPU follow-up is permitted."
        return await super().verify_reference_flow(reference, frames, duration_seconds)

    def _generate(self, images, prompt, frame_labels=None):
        folder = OUT / "followup"
        folder.mkdir()
        request = {"prompt": prompt, "frame_labels": frame_labels, "images": []}
        for index, image in enumerate(images):
            path = folder / f"frame-{index:02d}.jpg"
            path.write_bytes(image.data)
            request["images"].append({"file": path.name, "sha256": sha(image.data), "media_type": image.media_type})
        write_json(folder / "request.json", request)
        manifest["new_gpu_inference_calls"] += 1
        manifest["followup_image_count"] = len(images)
        write_json(OUT / "manifest.json", manifest)
        print(f"ONE real GPU follow-up: {len(images)} images; initial answer reused unchanged", flush=True)
        started = time.monotonic()
        try:
            raw = super()._generate(images, prompt, frame_labels)
            (folder / "response.txt").write_text(raw, encoding="utf-8")
            return raw
        finally:
            manifest["new_inference_seconds"] = round(time.monotonic() - started, 3)
            write_json(OUT / "manifest.json", manifest)


if __name__ == "__main__":
    if (OUT / "manifest.json").exists():
        raise SystemExit("Preserve this capture; use a new directory for another experiment.")
    original = ROOT / "docs/assets/video-demo/qwen3-web-auto-small"
    original_manifest = json.loads((original / "manifest.json").read_text(encoding="utf-8"))
    initial_file = original / "api-response.json"
    assert sha(initial_file.read_bytes()) == original_manifest["files"][initial_file.name]
    prior = json.loads(initial_file.read_text(encoding="utf-8"))
    source = ROOT / "docs/assets/video-demo/new-video-transfer/source.webm"
    assert sha(source.read_bytes()) == prior["source_sha256"] == original_manifest["source_sha256"]
    assert original_manifest["model_revision"] == REVISION
    (OUT / "reference-source.json").write_bytes((original / "reference-source.json").read_bytes())
    assert sha((OUT / "reference-source.json").read_bytes()) == original_manifest["reference_sha256"]
    manifest = {"executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "One NEW real follow-up with prior actual initial judgments frozen. Not two new GPU calls or a fresh upload.",
        "known_video": True, "accuracy_benchmark": False, "initial_reused": True,
        "initial_source": initial_file.relative_to(ROOT).as_posix(), "initial_source_sha256": sha(initial_file.read_bytes()),
        "source_sha256": prior["source_sha256"], "model": original_manifest["model"], "model_revision": REVISION,
        "load_in_4bit": True, "keep_vision_fp16": True, "max_pixels": 64*28*28, "max_new_tokens": 1200,
        "gpu": torch.cuda.get_device_name(0), "offline": True,
        "packages": {name: version(name) for name in ("torch", "transformers", "accelerate", "bitsandbytes")},
        "refinement_max_frames": 12, "requested_interval_seconds": .25,
        "new_gpu_inference_calls": 0, "status": "running", "code_sha256": {},
        "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()}
    for name in [Path(__file__).relative_to(ROOT).as_posix(),
        "providers/stepcheck_providers/reference_refinement.py", "providers/stepcheck_providers/reference_flow.py",
        "providers/stepcheck_providers/qwen_local_provider.py", "backend/app/infrastructure/video.py",
        "backend/app/application/verify_video_flow_use_case.py"]:
        data = (ROOT / name).read_bytes()
        manifest["code_sha256"][name] = sha(data)
        snapshot = OUT / "code" / name
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(data)
    write_json(OUT / "manifest.json", manifest)
    sampled = SampledVideo(prior["duration_seconds"],
        [read_video_frame(source, t) for t in prior["initial"]["sampled_seconds"]], prior["initial"]["sample_interval_seconds"])
    provider = FrozenInitialThenQwen(model=str(CACHE / "hub/models--Qwen--Qwen3-VL-4B-Instruct/snapshots" / REVISION),
        load_in_4bit=True, keep_vision_fp16=True, max_pixels=64*28*28, max_new_tokens=1200)
    started = time.monotonic()
    try:
        result = asyncio.run(VerifyVideoFlowUseCase(provider, manifest["model"]).execute(
            ReferenceFlow.model_validate(prior["reference"]), sampled, prior["source_sha256"],
            video=source, auto_refine=True, refinement_interval=.25, max_frames=12))
        result.update(analysis_mode="recorded_comparison", initial_reused=True, new_gpu_inference_calls=manifest["new_gpu_inference_calls"])
        write_json(OUT / "verification.json", result)
        manifest.update(status="validated_response", workflow=result["workflow"], order_status=result["order_status"])
    except Exception as exc:
        manifest.update(status="error", error=f"{type(exc).__name__}: {exc}")
    manifest["elapsed_seconds"] = round(time.monotonic() - started, 3)
    manifest["files"] = {p.relative_to(OUT).as_posix(): sha(p.read_bytes())
                         for p in sorted(OUT.rglob("*")) if p.is_file() and p.name != "manifest.json"}
    write_json(OUT / "manifest.json", manifest)
    print(json.dumps({k: manifest[k] for k in ("status", "new_gpu_inference_calls", "elapsed_seconds")}), flush=True)
