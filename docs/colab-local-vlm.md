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
既定の `FRAMEWISE=True` は1枚ずつ画像を認識し、観測文を同じモデルでフローに整理します。
モデルの観測文と整理結果は両方保存します。各段階に誤認・要約の誤りがありえるため、元画像との照合が必要です。
`FRAMEWISE=False` で全画像を一度に渡す方法も比較できます。
メモリー不足の場合は `MAX_IMAGE_PATCHES` または `MAX_FRAMES` を減らしてください。

モデルはフレームIDを根拠として返し、コードが実際の抽出時刻に対応付けます。
未提供のID、不正JSON、推論失敗はエラーにします。根拠を推測して補修したり、成功結果へ置き換えたりしません。
フレームの間の短い動作や、連続した運動の情報は見逃す可能性があります。
これは観測されたフローの抽出で、別に定義した手順への適合確認ではありません。

`/content/stepcheck-output/` に次を保存します。

- `flow.json`: 今回のモデル出力に基づく動作、根拠時刻、抽出画像、順番、動画SHA-256。
- `model-response.txt`: モデルの生出力。不正JSONでも保存します。
- `viewer.html`: 元動画と根拠画像を埋め込んだ、単独で開ける確認画面。
- `execution.json`: GPU、モデルのリビジョン、依存パッケージと実行時間。

`DOWNLOAD_RESULTS` を有効にすると、出力をZIPでダウンロードできます。
推論が失敗した再実行では前回の成功画面を残さず、生出力を保存してエラーにします。

動画と結果はColabランタイム内で処理します。ユーザー自身の動画を使った場合、出力ファイルにもその動画が含まれます。
ノートブック本体には実行出力を保存せず配布しています。

## Colabで実行して確認したこと

READMEの主GIFは、3B/FP16で24枚を個別認識した今回の実出力です。
モデルの動作名・時刻は未修正で、黄色のカードだけが推論後のCodexレビューです。
[以前の動画レビューによる7動作の基準](assets/video-demo/source-flow-baseline.json)と比較すると、
紙の取得と手拭きの混同、すすぎの時刻違い、最後のゴミ箱を「水槽」とする誤認が残りました。
**フロー全体とその順序は未確認です。** 基準の動作をモデルに教えて成功例を作ってはいません。

![Actual 3B framewise output and independent flow comparison](assets/qwen-3b-framewise.gif)

- [実際のレポート](assets/video-demo/qwen-3b-framewise-flow.json)
- [24枚の観測文とフロー整理の生出力](assets/video-demo/qwen-3b-framewise-raw.txt)
- [独立した根拠・基準フローとの比較](assets/video-demo/qwen-3b-framewise-review.json)
- [実行条件](assets/video-demo/qwen-3b-framewise-execution.json): T4、FP16、24枚、画像最大200,704画素、154.152秒（モデル読み込みを含む）。
- [実際の確認画面](assets/local-vlm-framewise-result.jpg): 元動画・抽出画像がゴミ箱を示す一方、モデルは「水槽」と報告しています。

保存済みの基準に対応する7動作について、別レビューに一致状況と隣接順序の確認状況を記録しています。
画像と時刻が実在すること、観測された動作が正しいこと、期待フロー全体に一致することをそれぞれ確認できます。
この比較は単一動画の検証で、モデル全体の精度評価ではありません。

次のコマンドで同じ認識方式を実行できます。

```bash
python scripts/run_local_video_flow.py docs/assets/video-demo/source.webm --framewise
```

### 初回3Bと7Bの比較記録

2026-10-08、T4（14.6 GiB）で同梱動画を24フレームに抽出し、3Bモデルの実推論とHTML確認画面まで実行しました。
初回は重み取得込みで150.1秒でした。ただし、初回のモデルは複数の動作に0秒を根拠として付け、
見えていない蛇口操作を報告しました。**実行できることと、認識が正しいことは別です。**

![Actual initial Qwen 3B inference with independent evidence review](assets/qwen-3b-initial.gif)

GIFは初回の未修正出力の再生です。モデルが出した動作名と時刻は変えていません。
黄色のカードは推論後にCodexが元フレームを見て付けた別のレビューです。
モデルのアテンションや確信度ではありません。
[実際のレポート](assets/video-demo/qwen-3b-initial-flow.json)、
[モデルの生出力](assets/video-demo/qwen-3b-initial-raw.txt)、
[別途行った根拠レビュー](assets/video-demo/qwen-3b-initial-review.json)を保存しています。

[確認画面のスクリーンショット](assets/local-vlm-result.jpg)も保存しました。
Colabから取得した初回結果を、元動画入りの単独HTMLで開いた画面です。
最初のフレームは石鹸ディスペンサー下の手で、「蛇口を開く」という判定を支えていないことが確認できます。

その後、画像の直前にID・時刻を置く入力へ変更すると、0秒への集中は改善しました。
ただし3Bは手拭きやゴミ箱付近を「消毒」と誤認し、6枚ごとの時間窓でも誤認が残りました。
現在の実装は画像IDを検証し、モデルの判定理由として表示します。IDが実在しても動作の意味が正しいとは限りません。

7B/NF4の一括認識も実行しました。24枚・画像最大200,704画素と100,352画素ではT4のメモリー不足で失敗しました。
50,176画素へ下げると推論は完了しましたが、手拭きの場面まで洗浄と判定し、7動作すべての根拠が重複しました。
この出力を成功例として扱っていません。
[未修正の一括認識レポート](assets/video-demo/qwen-7b-joint-flow.json)、
[生出力](assets/video-demo/qwen-7b-joint-raw.txt)、
[実行条件](assets/video-demo/qwen-7b-joint-execution.json)を保存しています。

7B/NF4で24枚を1枚ずつ認識し、観測文から整理する方式も実行しました（画像最大200,704画素）。
この実行では紙タオル装置を石鹸装置と誤認し、最終フローは「Soap Dispensing」「Hand Washing」の2動作にまとめられました。
1枚ずつ渡しても意味の誤認は解決しませんでした。
[個別認識のレポート](assets/video-demo/qwen-7b-framewise-flow.json)、
[24枚の観測文と整理応答](assets/video-demo/qwen-7b-framewise-raw.txt)、
[実行条件](assets/video-demo/qwen-7b-framewise-execution.json)を保存しています。
誤認の原因が量子化かモデル自体かは、この比較では切り分けていません。

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

より大きいモデルは4bit量子化でも読み込めます。`providers[local,quantized]` をインストールし、
CLIでは `--model Qwen/Qwen2.5-VL-7B-Instruct --load-in-4bit --framewise`、Web APIでは
`STEPCHECK_LOCAL_MODEL=Qwen/Qwen2.5-VL-7B-Instruct` と `STEPCHECK_LOCAL_LOAD_IN_4BIT=true` を指定します。
NF4で重みを圧縮し、計算はFP16で行います。モデルの重みは初回に取得するため、量子化してもダウンロードは必要です。
認識精度は別に評価してください。
ColabではGPU確認セルで7Bを選び、`LOAD_IN_4BIT` と `FRAMEWISE` を有効にします。
一括認識を比較する場合は `--image-patches 64`（Colabでは `MAX_IMAGE_PATCHES=64`）へ下げられます。
Web APIは一括認識です。個別認識の比較はColabまたはCLIを使ってください。

GPUのモデル重みは最初のリクエストで読み込み、その後のリクエストで再利用します。
画面にはローカルVLMで処理することを表示し、OpenAIへの送信案内と切り替えます。

ノートブックは `scripts/create_colab_notebook.py` で再生成できます（開発用に `nbformat` が必要です）。
JSONとPythonセルの構文、根拠ID検証、HTMLへのモデル文字列の埋め込みをテストしています。
これらのテストはモデルの認識精度を測るものではありません。

参考: [Qwen公式モデルカード](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct)、
[TransformersのQwen2.5-VLドキュメント](https://huggingface.co/docs/transformers/v4.57.1/en/model_doc/qwen2_5_vl)。
