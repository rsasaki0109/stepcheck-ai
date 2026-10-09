"""Export the captured, unmodified model verdicts with separate evidence review."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "providers")]
from verify_qwen3_video_flow import verification_replay_report
from stepcheck_providers.reference_flow import ReferenceFlow, ReferenceJudgment, build_reference_flow, compare_order


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    response = OUT / "api-response.json"
    if manifest["http_status"] != 200 or sha(response.read_bytes()) != manifest["files"][response.name]:
        raise ValueError("Require the intact successful API response, not an invented verdict.")
    result = json.loads(response.read_text(encoding="utf-8"))
    judgment = ReferenceJudgment(observations=[{k: s[k] for k in
        ("step_id", "status", "reason", "evidence_seconds", "uncertainty")} for s in result["steps"]])
    derived = build_reference_flow(ReferenceFlow.model_validate(result["reference"]), judgment,
                                    result["sampled_seconds"], result["duration_seconds"])
    if any(result[k] != derived[k] for k in ("steps", "transitions", "order_status")) or any(
            a != b for a, b in zip(result["initial"]["steps"], result["steps"]) if a["status"] == "observed"):
        raise ValueError("Inconsistent order, citations, or changed known judgment.")
    replay = verification_replay_report({**result, "model": manifest["model"], "input_modality": "sampled_images"},
        {**result, "frames": [{"timestamp_seconds": t} for t in result["sampled_seconds"]]})
    write_json(OUT / "replay.json", replay)
    reverse = compare_order(list(reversed(result["steps"])))
    labels = ["Wet", "Soap", "Lather", "Rinse", "Dry"]
    statuses = ["supported", "unknown", "unknown", "uncertain", "unknown"]
    audit = {"source_sha256": result["source_sha256"], "report_sha256": sha(json.dumps(replay,
        ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()),
        "reviewer": "Codex independent inspection of captured source JPEGs, after inference; known video",
        "notes": ["Wet citations show water contact. Rinse citations show water, but the model does not establish the prior visible-lather criterion.",
                  "Thin white patches are ambiguous; no supplied citation establishes soap application or drying. Unknown is not not_done."],
        "actions": [{"id": s["index"], "status": status} for s, status in zip(result["steps"], statuses)],
        "reference_flow": {"sequence": "wet > soap > lather > rinse > dry", "order_status": result["order_status"],
            "summary": "Model: 2 observed / 3 unknown. Rinse's prior-lather criterion unresolved. Full flow unknown.",
            "steps": [{"index": i+1, "label": label, "status": status}
                      for i, (label, status) in enumerate(zip(labels, statuses))]},
        "control_summary": f"Actual GPU: 12 initial + 9 follow-up images / {manifest['elapsed_seconds']:.0f}s. Recorded final output. Reverse: "
            + f"{sum(e['status']=='violated' for e in reverse['transitions'])} violations, {sum(e['status']=='unknown' for e in reverse['transitions'])} unknown."}
    write_json(OUT / "audit.json", audit)
    gif = ROOT / "docs/assets/qwen3-web-auto.gif"
    subprocess.run([sys.executable, str(ROOT / "scripts/generate_detected_flow_gif.py"),
        "--report", str(OUT / "replay.json"), "--audit", str(OUT / "audit.json"), "--output", str(gif),
        "--video", str(ROOT / "docs/assets/video-demo/new-video-transfer/source.webm"),
        "--source-credit", "Hand Washing / Anthony Albright / CC BY-SA 2.0 / Frames resized; verdicts + review added"], check=True)
    files = [response, OUT / "manifest.json", OUT / "replay.json", OUT / "audit.json", OUT / "GIF-ATTRIBUTION.md", gif,
             Path(__file__), ROOT / "scripts/generate_detected_flow_gif.py"]
    write_json(OUT / "replay-manifest.json", {"source_sha256": result["source_sha256"],
        "recognition_runs_during_export": 0, "model_verdicts_changed": False,
        "files": {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in files}})
