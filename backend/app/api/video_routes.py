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

from ..application.discover_flow_use_case import DiscoverFlowUseCase, report_with_frames
from ..config import Settings, get_settings
from ..infrastructure.video import (
    DecoderUnavailableError, SampledVideo, VideoDecodeError, VideoLimitError,
    decoder_ready, read_video_frame, sample_video,
)
from .dependencies import get_provider
from .schemas import VideoFlowOut

router = APIRouter(prefix="/video-flow", tags=["video flow"])
DEMO_ASSETS = Path(__file__).resolve().parents[3] / "docs" / "assets" / "video-demo"


@router.get("/status")
async def video_flow_status(settings: Settings = Depends(get_settings),
                            provider: VisionProvider = Depends(get_provider)) -> dict:
    reason = None
    if not provider.supports_flow:
        reason = "動画解析にはOpenAI接続、またはColabでローカルVLMを選択してください。"
    elif not await provider.health():
        reason = ("ローカルVLMにはGPUとlocal依存パッケージが必要です。" if provider.name == "qwen-local"
                  else "動画を解析するにはバックエンドに OPENAI_API_KEY を設定してください。")
    elif not decoder_ready():
        reason = "バックエンドに ffmpeg と ffprobe をインストールしてください。"
    return {"ready": reason is None, "provider": provider.name, "model": getattr(provider, "model_id", settings.model),
            "reason": reason, "max_video_bytes": settings.max_video_bytes,
            "max_video_seconds": settings.max_video_seconds,
            "max_video_frames": min(settings.max_video_frames, getattr(provider, "max_flow_frames", settings.max_video_frames))}


@router.post("", response_model=VideoFlowOut, summary="Discover an action flow from one uploaded video")
async def discover_video_flow(
    video: UploadFile = File(...),
    sample_interval_seconds: float = Form(0.75, ge=0.25, le=30, allow_inf_nan=False),
    settings: Settings = Depends(get_settings),
    provider: VisionProvider = Depends(get_provider),
) -> dict:
    try:
        if not provider.supports_flow:
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
            report = await DiscoverFlowUseCase(provider, getattr(provider, "model_id", settings.model)).execute(sampled, digest.hexdigest())
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
