"""Plot real selected timestamps; do not infer actions or spatial attention."""
from pathlib import Path
import hashlib
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


if __name__ == "__main__":
    old_file = ROOT / "docs/assets/video-demo/qwen3-web-auto-small/api-response.json"
    new_file = OUT / "verification.json"
    old = json.loads(old_file.read_text(encoding="utf-8"))
    new = json.loads(new_file.read_text(encoding="utf-8"))
    metadata = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    assert sha(old_file.read_bytes()) == metadata["initial_source_sha256"]
    assert sha(new_file.read_bytes()) == metadata["files"][new_file.name]
    assert old["source_sha256"] == new["source_sha256"] == metadata["source_sha256"]
    assert old["initial"] == new["initial"]
    initial = new["initial"]["sampled_seconds"]
    windows = new["refinement"]["windows"]

    def largest_gap(times):
        gaps = []
        for window in windows:
            a, b = window["start_seconds"], window["end_seconds"]
            points = sorted({a, b} | {t for t in times if a <= t <= b})
            gaps.extend(right-left for left, right in zip(points, points[1:]))
        return round(max(gaps, default=0), 6)

    before = largest_gap(initial)
    uniform = largest_gap(set(initial) | set(old["refinement"]["sampled_seconds"]))
    adaptive = largest_gap(set(initial) | set(new["refinement"]["sampled_seconds"]))
    assert adaptive == new["refinement"]["coverage"]["after_max_gap_seconds"]
    data = {"source_sha256": new["source_sha256"], "initial_reused": True,
            "same_followup_budget": 12, "before_max_gap_seconds": before,
            "uniform_after_max_gap_seconds": uniform, "gap_after_max_gap_seconds": adaptive,
            "recognition_improved": False, "uniform_order": old["order_status"], "gap_order": new["order_status"]}
    (OUT / "sampling-comparison.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    fig, ax = plt.subplots(figsize=(11, 4.6), layout="constrained")
    fig.patch.set_facecolor("#f8fafc")
    ax.set_facecolor("#f8fafc")
    for a, b in sorted({(w["start_seconds"], w["end_seconds"]) for w in windows}):
        ax.axvspan(a, b, color="#e2e8f0", alpha=.65, zorder=0)
    ax.scatter(initial, [2]*len(initial), color="#64748b", s=42, marker="|", linewidths=2, label="Prior review")
    for y, report, color in [(1, old, "#b45309"), (0, new, "#0f766e")]:
        added = report["refinement"]["added_seconds"]
        context = sorted(set(report["refinement"]["sampled_seconds"]) - set(added))
        ax.scatter(context, [y]*len(context), edgecolors=color, facecolors="none", s=52, linewidths=1.5)
        ax.scatter(added, [y]*len(added), color=color, s=48)
    ax.set_yticks([2, 1, 0], ["Frozen initial review: 12 images", "Uniform: 4 new + 5 context", "Gap bisection: 7 new + 5 context"])
    ax.set_xlim(-.4, new["duration_seconds"]+.4)
    ax.set_ylim(-.65, 2.5)
    ax.set_xticks(range(0, 33, 4))
    ax.set_xlabel("Source-video time (seconds)")
    ax.grid(axis="x", color="#cbd5e1", linewidth=.6)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0, pad=10)
    ax.set_title("Actual sampling comparison: full flow remains UNKNOWN", loc="left", fontsize=14, pad=18, weight="bold")
    ax.text(0, -.52, f"Largest reviewed-time gap in search windows: uniform {uniform:.2f}s / gap bisection {adaptive:.2f}s",
            fontsize=10, color="#334155")
    fig.text(.015, -.03, "Shading: search windows. Filled dots: new times. Hollow dots: required context.\n"
             "Same initial verdicts and 12-image budget. Soap, lather and drying stay unknown. Timing coverage is not recognition accuracy.",
             fontsize=9, color="#475569")
    svg = ROOT / "docs/assets/refinement-sampling-comparison.svg"
    fig.savefig(svg, bbox_inches="tight", metadata={"Date": None})
    fig.savefig(ROOT / ".tmp-flow-web-qa/sampling-comparison.png", bbox_inches="tight", dpi=150)
    files = [old_file, new_file, OUT / "manifest.json", OUT / "sampling-comparison.json", svg, Path(__file__)]
    (OUT / "sampling-chart-manifest.json").write_text(json.dumps({"files": {
        p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in files}}, indent=2), encoding="utf-8")
    print(json.dumps(data))
