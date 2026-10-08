"""Local GPU VLM inference and a self-contained source-video/evidence viewer."""

from __future__ import annotations

import argparse
import asyncio
import base64
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version, PackageNotFoundError
import json
import mimetypes
from pathlib import Path
import re
import sys
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "providers"), str(ROOT / "backend")]

from stepcheck_providers import create_provider  # noqa: E402
from app.application.discover_flow_use_case import report_with_frames  # noqa: E402
from app.infrastructure.video import sample_video  # noqa: E402


def render_viewer(report: dict, video: Path, destination: Path) -> Path:
    if hashlib.sha256(video.read_bytes()).hexdigest() != report["source_sha256"]:
        raise ValueError("Viewer source differs from the analyzed video.")
    serialized = json.dumps(report, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    media_type = mimetypes.guess_type(str(video))[0] or "video/mp4"
    source_url = f"data:{media_type};base64," + base64.b64encode(video.read_bytes()).decode("ascii")
    template = '''<!doctype html><html lang="ja"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box}body{font:15px/1.6 system-ui,sans-serif;background:#0b1120;color:#edf3fc;margin:0;padding:24px}
main{max-width:1080px;margin:auto}h1{font-size:24px}h2{font-size:18px}p{margin:8px 0}.muted{color:#9aaec8}
.badge{display:inline-block;background:#164e45;color:#8af2db;padding:4px 12px;border-radius:24px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:20px 0}.card{background:#121d30;border:1px solid #27364c;border-radius:14px;padding:18px;min-width:0}
video,img{width:100%;aspect-ratio:4/3;object-fit:contain;background:#050910;border-radius:8px}button{font:inherit;cursor:pointer;border:1px solid #33435c;border-radius:8px;background:#172439;color:#edf3fc;padding:9px 12px}
button.selected{border-color:#5eead4;background:#143e3e}.flow{display:flex;flex-direction:column;gap:8px;max-height:410px;overflow:auto}.flow button{text-align:left}.note{color:#fcd678}
.times{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.tiny{font-size:12px}@media(max-width:720px){body{padding:12px}.grid{grid-template-columns:1fr}}
</style><main id="stepcheck-viewer"><h1>StepCheck AI / ローカルVLMの動画フロー検出</h1>
<span id="mode" class="badge"></span><p id="title"></p><p id="meta" class="muted tiny"></p>
<div class="grid"><section class="card"><h2>元動画</h2><video id="source" controls playsinline preload="metadata" src="__SOURCE__"></video><p id="playback" class="muted tiny"></p></section>
<section class="card"><h2>検出したフロー</h2><div id="flow" class="flow"></div><p class="muted tiny">動作を選ぶと根拠時刻へ移動します。時刻は観測フレームを示し、動作の開始・終了を保証しません。</p></section></div>
<section class="card"><h2 id="selected-title">動作の根拠</h2><div class="grid"><div><img id="evidence" alt="選択した動作の根拠フレーム"><div id="times" class="times"></div></div>
<div><h2>モデルの判定理由</h2><p id="reason"></p><h2 class="note">モデルが報告した不明点</h2><p id="uncertainty" class="note"></p></div></div></section>
<details class="card" style="margin-top:20px"><summary>解析範囲と不明点</summary><ul id="limits"></ul></details></main>
<script>(()=>{const report=__REPORT__;const root=document.getElementById('stepcheck-viewer');const get=id=>root.querySelector('#'+id);
const seconds=t=>Number(t.toFixed(3))+'s';const video=get('source');let selected=null;
get('mode').textContent=report.analysis_mode==='live'?'この動画への実推論結果・根拠の確認が必要':'記録済み結果の再生';
get('title').textContent=report.title;get('meta').textContent=report.provider+' / '+report.model+' · '+report.frames.length+'フレーム · '+seconds(report.duration_seconds);
video.addEventListener('timeupdate',()=>get('playback').textContent='元動画 '+seconds(video.currentTime));
video.addEventListener('error',()=>get('playback').textContent='ブラウザーで元動画を再生できません。抽出した根拠画像で確認してください。');
function frameAt(t){const frame=report.frames.find(f=>f.timestamp_seconds===t);if(!frame)return;get('evidence').src=frame.image_url;get('evidence').alt=selected.label+' '+seconds(t);video.pause();if(video.readyState>=1)video.currentTime=t;
get('times').querySelectorAll('button').forEach(b=>b.classList.toggle('selected',Number(b.dataset.time)===t));}
function select(action){selected=action;get('selected-title').textContent=action.id+'. '+action.label+' の根拠';get('reason').textContent=action.reason;get('uncertainty').textContent=action.uncertainty||'モデルから個別の不明点は報告されていません。';
get('times').replaceChildren();for(const t of action.evidence_seconds){const b=document.createElement('button');b.textContent=seconds(t);b.dataset.time=t;b.onclick=()=>frameAt(t);get('times').append(b);}
get('flow').querySelectorAll('button').forEach(b=>b.classList.toggle('selected',Number(b.dataset.id)===action.id));frameAt(action.evidence_seconds[0]);}
video.addEventListener('loadedmetadata',()=>{if(selected)frameAt(selected.evidence_seconds[0]);});
report.actions.forEach((action,index)=>{if(index){const arrow=document.createElement('span');arrow.className='muted tiny';arrow.textContent=report.transitions[index-1]?.status==='ambiguous'?'↓ 順番は不明（根拠が重複）':'↓ 根拠フレームの順番';get('flow').append(arrow);}
const b=document.createElement('button');b.dataset.id=action.id;b.textContent=action.id+'. '+action.label+' / '+seconds(action.first_seen_seconds)+'–'+seconds(action.last_seen_seconds)+(action.uncertainty?' / 不明点あり':'');b.onclick=()=>select(action);get('flow').append(b);});
for(const value of report.limitations){const li=document.createElement('li');li.textContent=value;get('limits').append(li);}
if(report.actions.length)select(report.actions[0]);else{get('flow').textContent='動作を特定できませんでした。';get('evidence').hidden=true;get('reason').textContent='下の解析範囲と不明点を確認してください。';}
})();</script></html>'''
    replacements = {"__SOURCE__": source_url, "__REPORT__": serialized}
    destination.write_text(re.sub(r"__SOURCE__|__REPORT__", lambda match: replacements[match.group()], template), encoding="utf-8")
    return destination


async def run_local_flow(video: Path, output: Path, *, model: str = "Qwen/Qwen2.5-VL-3B-Instruct",
                         max_frames: int = 24, interval: float = 0.75, provider=None,
                         load_in_4bit: bool = False, image_patches: int = 256,
                         framewise: bool = False, keep_vision_fp16: bool = False) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    for name in ("flow.json", "viewer.html", "execution.json", "model-response.txt"):
        (output / name).unlink(missing_ok=True)
    if video.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("Video exceeds the 50 MiB limit.")
    sampled = await asyncio.to_thread(sample_video, video, interval, 120, max_frames)
    provider = provider or create_provider("qwen-local", model=model, load_in_4bit=load_in_4bit,
                                           max_pixels=image_patches * 28 * 28, framewise=framewise,
                                           keep_vision_fp16=keep_vision_fp16)
    executed_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    print(f"Recognizing {len(sampled.frames)} source frames with {model}; first run downloads model weights.", flush=True)
    try:
        detection = await provider.discover_flow(sampled.frames, sampled.duration_seconds)
    finally:
        (output / "model-response.txt").write_text(getattr(provider, "last_raw_response", ""), encoding="utf-8")
    report = report_with_frames(detection, sampled, provider=provider.name,
        source_sha256=hashlib.sha256(video.read_bytes()).hexdigest(), analysis_mode="live", model=model)
    (output / "flow.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    render_viewer(report, video, output / "viewer.html")
    packages = {}
    for name in ("torch", "transformers", "accelerate", "bitsandbytes"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            pass
    torch = sys.modules.get("torch")
    try:
        commit = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True, timeout=5).strip()
    except (OSError, subprocess.SubprocessError):
        commit = None
    execution = {"executed_at_utc": executed_at, "inference_seconds": round(time.monotonic() - started, 3),
        "repo_commit": commit, "model": model,
        "model_revision": getattr(getattr(getattr(provider, "_model", None), "config", None), "_commit_hash", None),
        "load_in_4bit": getattr(provider, "load_in_4bit", False),
        "framewise": getattr(provider, "framewise", False),
        "keep_vision_fp16": getattr(provider, "keep_vision_fp16", False),
        "max_pixels": getattr(provider, "max_pixels", None), "sample_count": len(sampled.frames),
        "gpu": torch.cuda.get_device_name(0) if torch is not None and torch.cuda.is_available() else None,
        "packages": packages, "source_sha256": report["source_sha256"]}
    (output / "execution.json").write_text(json.dumps(execution, indent=2), encoding="utf-8")
    return report


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / ".tmp-flow-local")
    parser.add_argument("--max-frames", type=int, default=24, choices=range(2, 33))
    parser.add_argument("--model", default="Qwen/Qwen2.5-VL-3B-Instruct")
    parser.add_argument("--load-in-4bit", action="store_true")
    parser.add_argument("--keep-vision-fp16", action="store_true",
                        help="Keep vision linear layers in FP16 when quantizing the language model.")
    parser.add_argument("--framewise", action="store_true",
                        help="Recognize each sampled image separately, then group its observations.")
    parser.add_argument("--image-patches", type=int, choices=(64, 128, 256, 1024), default=256,
                        help="Image pixel budget = value * 28 * 28, not the actual token count; use 64 for joint 7B on T4.")
    args = parser.parse_args()
    result = await run_local_flow(args.video, args.output, max_frames=args.max_frames,
                                  model=args.model, load_in_4bit=args.load_in_4bit,
                                  image_patches=args.image_patches, framewise=args.framewise,
                                  keep_vision_fp16=args.keep_vision_fp16)
    print(f"Recognized {len(result['actions'])} actions. Open {args.output / 'viewer.html'}")


if __name__ == "__main__":
    asyncio.run(main())
