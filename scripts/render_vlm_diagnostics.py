"""Render saved actual input diagnostics; this script never performs inference."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path

NAMES = ("stepcheck-input-diagnostics-3b", "stepcheck-input-diagnostics-7b-all4bit",
         "stepcheck-input-diagnostics-7b-vision-fp16", "stepcheck-native-video-7b")
OPTIONAL_NAMES = ("stepcheck-input-diagnostics-qwen3-4b",)


def render(directory: Path, video: Path, destination: Path):
    def asset(path):
        return Path(os.path.relpath(path.resolve(), destination.parent.resolve())).as_posix()

    source_hash = hashlib.sha256(video.read_bytes()).hexdigest()
    data = []
    frozen = {}
    names = [*NAMES, *(name for name in OPTIONAL_NAMES if (directory/name/"diagnostics.json").exists())]
    for name in names:
        folder = directory/name
        record = json.loads((folder/"diagnostics.json").read_text(encoding="utf-8"))
        if record["source_sha256"] != source_hash or record["expected_actions_supplied"]:
            raise ValueError("Diagnostics must use this source and no expected actions.")
        if not record["runs"] or record.get("status", "completed") != "completed":
            raise ValueError("Only completed actual diagnostics can be published.")
        native = record.get("input_modality") == "native_video"
        for run in record["runs"]:
            if not native:
                timestamp = run["timestamp_seconds"]
                blob = (folder/run["source_image"]).read_bytes()
                digest = hashlib.sha256(blob).hexdigest()
                if digest != run["image_sha256"] or frozen.get(timestamp, digest) != digest:
                    raise ValueError("Diagnostic variants must compare identical source JPEGs.")
                frozen[timestamp] = digest
                run["source_url"] = asset(folder/run["source_image"])
            actual = run.get("actual_input")
            if actual:
                if actual["image_token_count"] != actual["expected_image_token_count"]:
                    raise ValueError("Invalid visual placeholder count.")
                run["input_url"] = asset(folder/actual["reconstructed_image"])
        data.append({"name":name,"record":record})
    encoded = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    # Embedded media also seeks correctly with basic static servers lacking Range.
    source_url = "data:video/webm;base64,"+base64.b64encode(video.read_bytes()).decode("ascii")
    page = '''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>StepCheck AI — actual VLM input diagnostics</title><style>
*{box-sizing:border-box}body{margin:0;background:#0b1120;color:#e8effb;font:15px/1.6 system-ui,sans-serif;padding:24px}main{max-width:1100px;margin:auto}h1{font-size:25px;margin:0}h2{font-size:18px;margin:0 0 12px}.muted{color:#9dadc7}.note{color:#fcd678}select,button{font:inherit;background:#18263d;color:#e8effb;border:1px solid #455673;padding:9px;border-radius:8px}button{cursor:pointer}.controls{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}.card{background:#131e32;border:1px solid #2b3c55;border-radius:14px;padding:18px;margin-bottom:16px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}img,video{width:100%;object-fit:contain;background:#050911;border-radius:8px}img{aspect-ratio:4/3}video{max-height:340px}.raw{white-space:pre-wrap;overflow-wrap:anywhere;max-height:360px;overflow:auto}.tiny{font-size:12px}@media(max-width:720px){body{padding:12px}.grid{grid-template-columns:1fr}}
</style><main><h1>StepCheck AI / VLM入力と実応答の比較</h1>
<p class="muted">同じ動画・同じ保存JPEGを使った実推論。GPUとモデルは各実験の欄に記録しています。正解フローはモデルに与えていません。</p>
<p class="note">画像入力の整合性は確認できましたが、動作と全フローは未確認です。表示はアテンションマップではありません。</p>
<div class="controls"><select id="experiment" aria-label="実験"></select><select id="scene" aria-label="場面"></select><select id="variant" aria-label="入力条件"></select></div>
<p id="meta" class="muted tiny"></p><div id="images" class="grid"><section class="card"><h2>元の推論JPEG</h2><img id="source-image"><p id="source-caption" class="muted tiny"></p></section><section class="card"><h2>実テンソルから復元したモデル入力</h2><img id="input-image"><p id="input-caption" class="muted tiny"></p></section></div>
<section class="card"><h2>未修正のモデル応答</h2><div id="raw" class="raw"></div><p id="independent" class="note"></p></section>
<section class="card"><h2>同じ元動画を確認</h2><video id="video" controls playsinline preload="metadata" src="__VIDEO__"></video><div class="controls"><button id="seek">選択した時刻へ移動</button></div><p class="muted tiny">全編・区間の動画入力は画像の時間的なまとまりを渡します。表示する区間は抽出範囲で、動作の開始・終了時刻ではありません。</p></section>
<details><summary>実行条件と限界</summary><p id="conditions" class="tiny"></p><p>画像の色・位置・順番、視覚トークン数を確認する診断です。入力が正しくても、モデルの説明が正しいことは保証しません。復元画像はアテンションや内部特徴ではありません。動画入力の出力は時刻付きフローレポートへ自動変換していません。</p></details></main>
<script>const data=__DATA__;const $=id=>document.getElementById(id);
const titles=data.map(({record:r})=>`${r.model.split('/').pop()} / ${r.load_in_4bit?'NF4'+(r.keep_vision_fp16?' + 視覚FP16':'（視覚も4bit）'):'FP16'}${r.input_modality==='native_video'?' / 動画入力':''}`);
const scenes=['13.941s / 紙を取る場面','17.924s / 手を拭く場面','21.907s / 紙越しに取っ手を持つ場面','22.903s / 紙をゴミ箱へ下ろす場面'];
const observations=['独立レビュー: 元動画では紙タオルの取得。単一画像だけでは引く動きを断定できません。','独立レビュー: 元動画では紙タオルで手を拭く場面。装置からの紙の取得はその前の場面です。','独立レビュー: 紙越しにドアの取っ手を保持。開扉は確認できません。','独立レビュー: 紙タオルを内袋付きゴミ箱へ下ろす場面。手からの離脱は隠れています。'];
function options(element,values){element.replaceChildren();values.forEach((value,index)=>{const option=document.createElement('option');option.value=index;option.textContent=value;element.append(option);});}
options($('experiment'),titles);options($('scene'),scenes);
let selectedRun;
function changeExperiment(){const record=data[+$('experiment').value].record;const native=record.input_modality==='native_video';$('scene').hidden=native;options($('variant'),[...new Set(record.runs.map(r=>r.variant))]);show();}
function show(){const record=data[+$('experiment').value].record;const native=record.input_modality==='native_video';const variants=[...new Set(record.runs.map(r=>r.variant))];const variant=variants[+$('variant').value];let run;
if(native){run=record.runs.find(r=>r.variant===variant);}else{const times=[...new Set(record.runs.map(r=>r.timestamp_seconds))];run=record.runs.find(r=>r.variant===variant&&r.timestamp_seconds===times[+$('scene').value]);}selectedRun=run;
$('source-image').parentElement.hidden=native;$('images').style.display=native?'block':'grid';
$('input-image').style.aspectRatio=native?'auto':'4/3';$('input-image').style.maxHeight=native?'600px':'none';
$('source-image').hidden=native;$('source-caption').textContent=native?'元動画の順番を維持した保存24枚から入力。':`${run.timestamp_seconds}s · JPEG SHA256 ${run.image_sha256}`;if(!native)$('source-image').src=run.source_url;
$('input-image').hidden=!run.input_url;if(run.input_url)$('input-image').src=run.input_url;
const actual=run.actual_input;$('input-caption').textContent=actual?`${actual.reconstructed_size.join(' × ')} · ${actual.image_token_count} visual tokens · grid ${JSON.stringify(actual.image_grid_thw||actual.video_grid_thw)}`:run.error;
$('raw').textContent=run.model_response||run.error;$('independent').textContent=native?'独立レビュー: 動画入力でも根拠のない蛇口操作、動作の混同・欠落が残ります。全フローの一致と順序は未確認。':observations[+$('scene').value];
$('meta').textContent=`${record.model} · ${record.gpu} · ${variant} · ${run.inference_seconds}s`;$('conditions').textContent=`実行: ${record.executed_at_utc} / モデルrevision: ${record.model_revision} / 動画SHA256: ${record.source_sha256} / Prompt: ${record.prompt}`;
}
$('experiment').addEventListener('change',changeExperiment);$('scene').addEventListener('change',show);$('variant').addEventListener('change',show);$('seek').addEventListener('click',()=>{const record=data[+$('experiment').value].record;$('video').currentTime=selectedRun.timestamp_seconds??record.sample_timestamps_seconds[selectedRun.source_frame_ids[0]];});changeExperiment();</script></html>'''
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(page.replace("__VIDEO__", source_url).replace("__DATA__", encoded), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    parser.add_argument("video",type=Path)
    parser.add_argument("destination",type=Path)
    args = parser.parse_args()
    render(args.directory,args.video,args.destination)
