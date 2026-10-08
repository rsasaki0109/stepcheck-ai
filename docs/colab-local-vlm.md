# ColabでローカルVLMを使う

[Colabで開く](https://colab.research.google.com/github/rsasaki0109/stepcheck-ai/blob/main/notebooks/stepcheck_local_vlm.ipynb)

`Qwen/Qwen2.5-VL-3B-Instruct` の公開重みをダウンロードし、ColabランタイムのGPUで推論します。
OpenAI APIキーや有料の推論APIは使いません。GPUの割り当てはColab側の利用状況によります。

1. ランタイムのタイプを **T4 GPU** に変更します。
2. セットアップ、GPU確認、動画選択、実推論、確認画面の順にセルを実行します。
3. 標準では同梱のCDC手洗い動画を今回のモデルで解析します。保存済みのCodexレビューや期待フローは読みません。
4. 別の動画は `UPLOAD_VIDEO` を有効にして1本アップロードします。
5. 検出された動作を選ぶと、元動画の時刻、根拠画像、理由、不明点を確認できます。

モデルはFP16、SDPAで読み込みます。初回にはモデルのダウンロードが必要です。
既定では動画全体から最大24フレームを抽出し、画像あたりの解像度を抑えてGPUメモリーを制限します。
メモリー不足の場合は `MAX_FRAMES` を16または8に減らしてください。

モデルはフレームIDを根拠として返し、コードが実際の抽出時刻に対応付けます。
未提供のID、不正JSON、推論失敗はエラーにします。根拠を推測して補修したり、成功結果へ置き換えたりしません。
フレームの間の短い動作や、連続した運動の情報は見逃す可能性があります。
これは観測されたフローの抽出で、別に定義した手順への適合確認ではありません。

`/content/stepcheck-output/` に次を保存します。

- `flow.json`: 今回のモデル出力に基づく動作、根拠時刻、抽出画像、順番、動画SHA-256。
- `model-response.txt`: モデルの生出力。不正JSONでも保存します。
- `viewer.html`: 元動画と根拠画像を埋め込んだ、単独で開ける確認画面。

動画と結果はColabランタイム内で処理します。ユーザー自身の動画を使った場合、出力ファイルにもその動画が含まれます。
ノートブック本体には実行出力を保存せず配布しています。

## 同じモデルをローカルやWeb APIで使う

CUDA GPUのある環境で:

```bash
python -m pip install -e "./providers[local]" -e ./backend
python scripts/run_local_video_flow.py docs/assets/video-demo/source.webm
```

`ffmpeg` と `ffprobe` を `PATH` に置いてください。CLIの出力先は `.tmp-flow-local/` です。

Webバックエンドでも同じプロバイダーを選べます。

```dotenv
STEPCHECK_PROVIDER=qwen-local
STEPCHECK_LOCAL_MODEL=Qwen/Qwen2.5-VL-3B-Instruct
STEPCHECK_MAX_VIDEO_FRAMES=24
```

GPUのモデル重みは最初のリクエストで読み込み、その後のリクエストで再利用します。
画面にはローカルVLMで処理することを表示し、OpenAIへの送信案内と切り替えます。

ノートブックは `scripts/create_colab_notebook.py` で再生成できます（開発用に `nbformat` が必要です）。
JSONとPythonセルの構文、根拠ID検証、HTMLへのモデル文字列の埋め込みをテストしています。
これらのテストはモデルの認識精度を測るものではありません。

参考: [Qwen公式モデルカード](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct)、
[TransformersのQwen2.5-VLドキュメント](https://huggingface.co/docs/transformers/v4.57.1/en/model_doc/qwen2_5_vl)。
