"""Video upload, open-ended flow recognition, and an explicitly recorded demo."""

import asyncio
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from stepcheck_providers import VisionProvider
from stepcheck_providers.flow import Detection, FlowInferenceError, FlowUnavailableError
from stepcheck_providers.reference_flow import ReferenceFlow, ReferenceJudgment

from ..application.discover_flow_use_case import DiscoverFlowUseCase, report_with_frames
from ..application.verify_video_flow_use_case import VerifyVideoFlowUseCase, reference_report_with_frames
from ..config import Settings, get_settings
from ..infrastructure.video import (
    DecoderUnavailableError, SampledVideo, VideoDecodeError, VideoLimitError,
    decoder_ready, read_video_frame, sample_video,
)
from .dependencies import get_provider
from .schemas import VideoFlowOut, VideoReferenceOut

router = APIRouter(prefix="/video-flow", tags=["video flow"])
DEMO_ASSETS = Path(__file__).resolve().parents[3] / "docs" / "assets" / "video-demo"


@router.get("/status")
async def video_flow_status(settings: Settings = Depends(get_settings),
                            provider: VisionProvider = Depends(get_provider)) -> dict:
    connection_reason = None
    if provider.supports_flow or provider.supports_reference_flow:
        if not await provider.health():
            connection_reason = ("ローカルVLMにはGPUとlocal依存パッケージが必要です。" if provider.name == "qwen-local"
                  else "動画を解析するにはバックエンドに OPENAI_API_KEY を設定してください。")
        elif not decoder_ready():
            connection_reason = "バックエンドに ffmpeg と ffprobe をインストールしてください。"
    reason = connection_reason if provider.supports_flow else "動画解析にはOpenAI接続、またはColabでローカルVLMを選択してください。"
    reference_reason = connection_reason if provider.supports_reference_flow else "工程の動画確認にはOpenAI接続、またはローカルQwenの設定が必要です。"
    return {"ready": reason is None, "provider": provider.name, "model": getattr(provider, "model_id", settings.model),
            "reason": reason, "max_video_bytes": settings.max_video_bytes,
            "reference_ready": reference_reason is None, "reference_reason": reference_reason,
            "max_video_seconds": settings.max_video_seconds,
            "max_video_frames": min(settings.max_video_frames, getattr(provider, "max_flow_frames", settings.max_video_frames))}


@router.post("", response_model=VideoFlowOut, summary="Discover an action flow from one uploaded video")
async def discover_video_flow(
    video: UploadFile = File(...),
    sample_interval_seconds: float = Form(0.75, ge=0.25, le=30, allow_inf_nan=False),
    settings: Settings = Depends(get_settings),
    provider: VisionProvider = Depends(get_provider),
) -> dict:
    return await analyze_upload(video, sample_interval_seconds, settings, provider)


@router.post("/verify", response_model=VideoReferenceOut, summary="Check given steps and sample order in one uploaded video")
async def verify_video_flow(
    video: UploadFile = File(...),
    reference_json: str = Form(..., max_length=65536),
    sample_interval_seconds: float = Form(0.75, ge=0.25, le=30, allow_inf_nan=False),
    settings: Settings = Depends(get_settings),
    provider: VisionProvider = Depends(get_provider),
) -> dict:
    return await analyze_upload(video, sample_interval_seconds, settings, provider, reference_json)


async def analyze_upload(video, sample_interval_seconds, settings, provider, reference_json=None):
    try:
        reference = None
        if reference_json is not None:
            try:
                reference = ReferenceFlow.model_validate_json(reference_json)
            except ValueError as exc:
                raise HTTPException(422, "Invalid reference JSON: require a title and unique nonempty step IDs/labels (1–30 steps).") from exc
        supported = provider.supports_reference_flow if reference else provider.supports_flow
        if not supported:
            raise FlowUnavailableError("Select openai or qwen-local; mock does not recognize videos.")
        if not await provider.health():
            raise FlowUnavailableError("The selected provider is not ready. Check its credentials or local GPU/dependencies.")
        with tempfile.TemporaryDirectory(prefix="stepcheck-video-") as directory:
            path = Path(directory) / "upload.video"
            size = 0
            digest = hashlib.sha256()
            with path.open("wb") as target:
                while chunk := await video.read(1024 * 1024):
                    size += len(chunk)
                    if size > settings.max_video_bytes:
                        raise HTTPException(413, "Video exceeds the upload size limit.")
                    target.write(chunk)
                    digest.update(chunk)
            if size == 0:
                raise HTTPException(400, "A non-empty video is required.")
            frame_limit = min(settings.max_video_frames, getattr(provider, "max_flow_frames", settings.max_video_frames))
            sampled = await asyncio.to_thread(sample_video, path, sample_interval_seconds,
                                              settings.max_video_seconds, frame_limit)
            model = getattr(provider, "model_id", settings.model)
            if reference:
                report = await VerifyVideoFlowUseCase(provider, model).execute(reference, sampled, digest.hexdigest())
            else:
                report = await DiscoverFlowUseCase(provider, model).execute(sampled, digest.hexdigest())
        return report
    except (FlowUnavailableError, DecoderUnavailableError) as exc:
        raise HTTPException(503, str(exc)) from exc
    except VideoLimitError as exc:
        raise HTTPException(413, str(exc)) from exc
    except VideoDecodeError as exc:
        raise HTTPException(422, str(exc)) from exc
    except FlowInferenceError as exc:
        raise HTTPException(502, str(exc)) from exc
    finally:
        await video.close()


@lru_cache(maxsize=1)
def load_demo() -> dict:
    source = DEMO_ASSETS / "source.webm"
    recorded = json.loads((DEMO_ASSETS / "detected-flow.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != recorded["source_sha256"]:
        raise FlowInferenceError("Recorded demo does not match the bundled source video.")
    detection = Detection(title=recorded["title"], limitations=recorded["limitations"], actions=[
        {key: action[key] for key in ("label", "reason", "evidence_seconds", "uncertainty")}
        for action in recorded["actions"]
    ])
    sampled = SampledVideo(recorded["duration_seconds"],
                           [read_video_frame(source, timestamp) for timestamp in recorded["sampled_seconds"]], 0.75)
    return report_with_frames(detection, sampled, provider="codex", source_sha256=digest,
                              analysis_mode="recorded_demo", model=recorded["reviewer"])


@router.get("/demo", response_model=VideoFlowOut)
async def demo_flow() -> dict:
    """Replay saved Codex observations of the bundled source; does not run inference."""
    try:
        if not decoder_ready():
            raise DecoderUnavailableError("Install ffmpeg and ffprobe to load demo evidence frames.")
        return await asyncio.to_thread(load_demo)
    except (DecoderUnavailableError, FileNotFoundError) as exc:
        raise HTTPException(503, "The recorded demo source or video decoder is unavailable.") from exc
    except (FlowInferenceError, VideoDecodeError) as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/demo/video")
async def demo_video() -> FileResponse:
    source = DEMO_ASSETS / "source.webm"
    if not source.is_file():
        raise HTTPException(404, "The recorded demo video is unavailable.")
    return FileResponse(source, media_type="video/webm")


@lru_cache(maxsize=1)
def load_reference_demo() -> dict:
    assets = DEMO_ASSETS / "automatic-reference-workflow"
    source = DEMO_ASSETS / "new-video-transfer/source.webm"
    saved = json.loads((assets / "verification.json").read_text(encoding="utf-8"))
    initial = json.loads((assets / "initial-verification.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != saved["source_sha256"] or digest != initial["source_sha256"]:
        raise FlowInferenceError("Reference demo does not match its source video.")
    prior_digest = hashlib.sha256(json.dumps(initial, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode("utf-8")).hexdigest()
    if saved["refinement"]["prior_report_sha256"] != prior_digest:
        raise FlowInferenceError("Reference demo initial report does not match refinement provenance.")
    reference = ReferenceFlow.model_validate(saved["reference"])
    if reference != ReferenceFlow.model_validate(initial["reference"]):
        raise FlowInferenceError("Reference demo changed its reference.")
    fields = ("step_id", "status", "reason", "evidence_seconds", "uncertainty")
    def judgment(report):
        return ReferenceJudgment(observations=[{key: s[key] for key in fields} for s in report["steps"]])
    from stepcheck_providers.reference_flow import build_reference_flow
    # Validate both recorded passes and deterministic order before any decoding.
    checked = build_reference_flow(reference, judgment(saved), saved["sampled_seconds"], saved["duration_seconds"])
    first = build_reference_flow(reference, judgment(initial), initial["sampled_seconds"], initial["duration_seconds"])
    for report, derived in ((saved, checked), (initial, first)):
        if any(report[key] != derived[key] for key in ("steps", "transitions", "order_status")):
            raise FlowInferenceError("Reference demo differs from its cited evidence.")
    for before, after in zip(first["steps"], checked["steps"]):
        if before["status"] == "observed" and before != after:
            raise FlowInferenceError("Reference demo changed prior observed judgments.")
    sampled = SampledVideo(saved["duration_seconds"],
        [read_video_frame(source, t) for t in saved["sampled_seconds"]], None)
    report = reference_report_with_frames(reference, judgment(saved), sampled, provider="codex-mcp",
        source_sha256=digest, analysis_mode="recorded_demo", model=saved["reviewer"])
    return {**report, "initial": first, "workflow": saved["workflow"],
        "source_credit": "Anthony Albright / Hand Washing. CC BY-SA 2.0. https://commons.wikimedia.org/wiki/File:Hand_Washing_video.webm . Changes: source frames sampled/resized; recorded judgments displayed. No endorsement implied."}


@router.get("/reference-demo", response_model=VideoReferenceOut)
async def reference_demo():
    """Two actual Codex MCP passes replayed without invoking any vision provider."""
    try:
        if not decoder_ready():
            raise DecoderUnavailableError("Install ffmpeg and ffprobe to load demo evidence.")
        return await asyncio.to_thread(load_reference_demo)
    except (DecoderUnavailableError, FileNotFoundError) as exc:
        raise HTTPException(503, "Reference demo source or decoder unavailable.") from exc
    except (FlowInferenceError, VideoDecodeError, ValueError, KeyError) as exc:
        raise HTTPException(502, "Recorded reference demo failed evidence validation or decoding.") from exc


@router.get("/reference-demo/video")
async def reference_demo_video():
    source = DEMO_ASSETS / "new-video-transfer/source.webm"
    if not source.is_file():
        raise HTTPException(404, "Reference demo video unavailable.")
    return FileResponse(source, media_type="video/webm")
