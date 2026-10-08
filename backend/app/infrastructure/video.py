"""Bounded FFmpeg decoding; timestamps refer to the exact requested source frames."""

from dataclasses import dataclass
import json
import math
from pathlib import Path
import shutil
import subprocess

from stepcheck_providers import ImagePayload
from stepcheck_providers.flow import VideoFrame


class VideoDecodeError(ValueError):
    pass


class VideoLimitError(ValueError):
    pass


class DecoderUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class SampledVideo:
    duration_seconds: float
    frames: list[VideoFrame]
    sample_interval_seconds: float


def decoder_ready() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def inspect_duration(path: Path, max_duration_seconds: float) -> float:
    if not decoder_ready():
        raise DecoderUnavailableError("Install ffmpeg and ffprobe on the backend PATH.")
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", "-select_streams", "v:0",
             "-show_entries", "format=duration:stream=width,height", "-of", "json", str(path)],
            capture_output=True, check=True, timeout=15,
        )
        info = json.loads(result.stdout)
        duration = float(info["format"]["duration"])
        if not info.get("streams") or not math.isfinite(duration) or duration <= 0:
            raise ValueError("No finite-duration video stream.")
    except (subprocess.SubprocessError, ValueError, KeyError, TypeError) as exc:
        raise VideoDecodeError("This file could not be read as a video.") from exc
    if duration > max_duration_seconds:
        raise VideoLimitError(f"Video exceeds the {max_duration_seconds:g}-second duration limit.")
    return duration


def read_video_frame(path: Path, timestamp: float) -> VideoFrame:
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-protocol_whitelist", "file,pipe",
             "-ss", f"{timestamp:.6f}", "-i", str(path), "-frames:v", "1", "-vf",
             "scale=640:640:force_original_aspect_ratio=decrease", "-q:v", "4",
             "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
            capture_output=True, check=True, timeout=15,
        )
        if not result.stdout:
            raise ValueError("No decoded frame.")
    except (subprocess.SubprocessError, ValueError) as exc:
        raise VideoDecodeError(f"Unable to decode the frame at {timestamp:g}s.") from exc
    return VideoFrame(timestamp_seconds=timestamp, image=ImagePayload(result.stdout, "image/jpeg"))


def sample_video(path: Path, interval: float, max_duration: float, max_frames: int) -> SampledVideo:
    duration = inspect_duration(path, max_duration)
    if not math.isfinite(interval) or interval <= 0 or max_frames < 2:
        raise ValueError("A positive interval and at least two frames are required.")
    end = max(0, duration - min(0.1, duration / 2))
    # Increase spacing rather than truncate a long video's tail.
    effective_interval = max(interval, end / (max_frames - 1))
    count = min(max_frames - 1, math.floor(end / effective_interval) + 1)
    times = sorted(set([round(i * effective_interval, 6) for i in range(count)] + [round(end, 6)]))
    frames = [read_video_frame(path, timestamp) for timestamp in times]
    return SampledVideo(duration, frames, effective_interval)
