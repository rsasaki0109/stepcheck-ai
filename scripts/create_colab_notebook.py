"""Generate the keyless, local-GPU video-flow notebook (requires nbformat)."""

from pathlib import Path
import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]


def main():
    notebook = nbf.v4.new_notebook()
    notebook.metadata = {"colab": {"name": "StepCheck AI — Local VLM video flow", "provenance": []},
                         "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                         "language_info": {"name": "python"}, "accelerator": "GPU"}
    notebook.cells = [
        nbf.v4.new_markdown_cell("""# StepCheck AI: 1本の動画からフローを検出（ローカルVLM）

**OpenAI APIキー不要。Qwen2.5-VL-3B-InstructをColabのGPUで実行します。**

1. **ランタイム → ランタイムのタイプを変更 → T4 GPU** を選びます。
2. 上から順にセルを実行します。標準では公開の手洗い動画を解析します。
3. 自分の動画を試すときは動画選択セルの `UPLOAD_VIDEO` を有効にします。
4. 動作をクリックして、根拠フレーム・時刻・理由・不明点を確認します。

初回はモデルのダウンロードが必要です。GPU推論はこのColabランタイム内で動作します。
動画から抽出したフレームを使うため、短い動作の見逃しや誤認識はありえます。
表示する結果は今回の推論で生成し、以前のCodexレビューはモデルに渡しません。
"""),
        nbf.v4.new_code_cell('''# 1. セットアップ（APIキー不要）
import subprocess
import sys
from pathlib import Path

REPO = Path("/content/stepcheck-ai")
REPO_REF = "main"
if not REPO.exists():
    subprocess.run(["git", "clone", "--depth", "1", "--branch", REPO_REF,
                    "https://github.com/rsasaki0109/stepcheck-ai.git", str(REPO)], check=True)
subprocess.run(["apt-get", "-qq", "update"], check=True)
subprocess.run(["apt-get", "-qq", "install", "-y", "ffmpeg"], check=True)
subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                "transformers==4.57.1", "accelerate>=1.0,<2",
                "-e", str(REPO / "providers") + "[local]",
                "-e", str(REPO / "backend")], check=True)
sys.path[:0] = [str(REPO / "scripts"), str(REPO / "providers"), str(REPO / "backend")]
print("Repository commit:")
subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], check=True)
print("セットアップ完了")'''),
        nbf.v4.new_code_cell('''# 2. GPUを確認（モデルは次の推論セルで読み込みます）
import torch
assert torch.cuda.is_available(), "ランタイムのタイプをT4 GPUに変更して、上から実行してください。"
print("GPU:", torch.cuda.get_device_name(0))
print("VRAM:", round(torch.cuda.get_device_properties(0).total_memory / 2**30, 1), "GiB")
MODEL_ID = "Qwen/Qwen2.5-VL-3B-Instruct"
MAX_FRAMES = 24  # GPUメモリーが足りない場合は16または8へ減らす
print("Local model:", MODEL_ID)'''),
        nbf.v4.new_code_cell('''# 3. 動画を選択（標準は同梱の公開動画）
UPLOAD_VIDEO = False #@param {type:"boolean"}
if UPLOAD_VIDEO:
    from google.colab import files
    uploaded = files.upload()
    if len(uploaded) != 1:
        raise ValueError("動画を1本だけ選択してください。")
    VIDEO_PATH = Path(next(iter(uploaded))).resolve()
else:
    VIDEO_PATH = REPO / "docs/assets/video-demo/source.webm"
print("Source:", VIDEO_PATH.name, "Bytes:", VIDEO_PATH.stat().st_size)
# 同梱動画: CDCの公開動画。https://commons.wikimedia.org/wiki/File:Clean_hands_short.webm'''),
        nbf.v4.new_code_cell('''# 4. 今回の動画に対して実推論（以前のレビューや正解フローは読み込みません）
import json
import time
from stepcheck_providers import create_provider
from run_local_video_flow import run_local_flow

OUTPUT_DIR = Path("/content/stepcheck-output")
if "provider" not in globals() or provider.model_id != MODEL_ID:
    provider = create_provider("qwen-local", model=MODEL_ID)
started = time.monotonic()
report = await run_local_flow(VIDEO_PATH, OUTPUT_DIR, model=MODEL_ID,
                               max_frames=MAX_FRAMES, provider=provider)
print("Inference seconds:", round(time.monotonic() - started, 1))
print(json.dumps({key: report[key] for key in ("title", "actions", "transitions", "limitations")},
                  ensure_ascii=False, indent=2))
print("Raw model output:", OUTPUT_DIR / "model-response.txt")'''),
        nbf.v4.new_code_cell('''# 5. 動作をクリックして根拠を確認
from IPython.display import HTML, display
display(HTML((OUTPUT_DIR / "viewer.html").read_text(encoding="utf-8")))'''),
        nbf.v4.new_markdown_cell("""## 出力と再実行

`/content/stepcheck-output/` に次のファイルを保存します。

- `flow.json`: 今回の認識結果、根拠時刻、抽出フレーム、動画SHA-256。
- `model-response.txt`: ローカルモデルの生出力。
- `viewer.html`: 元動画と根拠画像を含む、単独で開ける確認画面。

別の動画は動画選択セルから、GPUメモリー不足は `MAX_FRAMES` を減らして再実行します。
JSONや根拠IDが不正なモデル出力はエラーにします。見えない動作を補完したり、成功結果に置き換えたりしません。
手順全体の正しさを検証するには、別に期待フローを定義して比較する必要があります。

[モデルカード](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct) ·
[コード](https://github.com/rsasaki0109/stepcheck-ai) ·
[使い方](https://github.com/rsasaki0109/stepcheck-ai/blob/main/docs/colab-local-vlm.md)
"""),
    ]
    destination = ROOT / "notebooks" / "stepcheck_local_vlm.ipynb"
    destination.parent.mkdir(exist_ok=True)
    nbf.validate(notebook)
    nbf.write(notebook, destination)
    print(destination)


if __name__ == "__main__":
    main()
