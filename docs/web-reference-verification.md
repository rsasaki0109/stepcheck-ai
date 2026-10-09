# Webで1本の動画と工程の順序を確認する

トップ画面の「動画で工程と順序を確認」で、工程名・何が見えれば確認できるか・期待する順番を編集し、
動画を1本アップロードできます。工程の追加・削除・上下移動に対応しています。

「この動画で工程を確認」は、設定したOpenAIまたはローカルQwenへ実際の動画サンプルを渡す処理です。
`mock`は動画の判定を作りません。モデルが未接続のときは実行ボタンを無効にします。
モデルの認識結果は候補として扱い、工程ごとの引用画像・理由・不確実性から確認します。

結果では、4区間のレビュー画像、元動画、工程ごとの根拠画像を表示します。
工程や時刻を選ぶと元動画へ移動できます。根拠がない未確認の工程には、別の工程の画像を流用しません。
基準・順序・動画・画像間隔を変更すると以前の判定を消し、条件が違う結果を混ぜません。

## 判定と順序

動画の工程判定は`observed`（観測あり）と`unknown`（未確認）の2つです。
画面外や画像が足りない工程を「未実施」とは判定しません。信頼度やヒートマップは生成しません。

隣り合う工程の引用画像を比較し、前工程の最大時刻が次工程の最小時刻より早ければ`sampled_before`、
引用時刻が完全に逆なら`violated`、重なりや未確認があれば`unknown`です。
順序の計算はMCP・ローカル検証スクリプトと共有しています。
これはサンプル画像の順序であり、連続した実行や動作の開始・終了を測ったものではありません。

**Webアップロードは初回の判断を実行します。自動追加確認はこのAPIではまだ実行しません。**
初回から追加確認までのMCP制御は[自動ワークフロー](automatic-reference-workflow.md)で使えます。

## キーなしで前回の実MCP結果を見る

「記録済みの工程確認を見る」は、32秒の映像に対する前回の実Codex MCP判断を再生します。
新しい推論や、アップロードした動画への判定には使いません。

- 初回と最終結果を切り替え、引用画像の違いを確認できます。
- 4工程は観測あり、乾燥は追加確認後も未確認、全体の順序も未確認です。
- 2回の画像判断と、0.25秒間隔が予算超過して0.5秒になった記録を表示します。
- 元動画・初回結果のハッシュ、両段階の引用と順序、既に観測した判断の維持を検証してから画像を読み込みます。

映像はAnthony Albright「Hand Washing」のCC BY-SA 2.0素材です。
元動画からの画像抽出・縮小と記録済み判断の表示を行っています。
[出典](assets/video-demo/automatic-reference-workflow/ATTRIBUTION.md)と
[実MCP要求・回答](automatic-reference-workflow.md#実動画で動かした結果)を参照してください。

## API

`POST /api/video-flow/verify`はmultipartで次を受け取ります。

| フィールド | 内容 |
|---|---|
| `video` | 元動画1本。既存の容量・時間制限を適用 |
| `reference_json` | `title`と`steps`。工程は一意な`id`、`label`、任意の`criterion`。1〜30工程、JSONは最大65,536文字 |
| `sample_interval_seconds` | 希望する間隔。初期値0.75秒、0.25〜30秒 |

画像上限に合わせて間隔を広げ、末尾までサンプリングします。ローカルQwenでは最大24枚です。
動画は一時ファイルに保存し、リクエスト終了時に削除します。モデルにはサンプル画像と基準を渡します。
モデルが返した工程IDや引用時刻を検証し、工程の欠落・重複・未提供の引用を502エラーで拒否します。
不正な基準は422、容量・時間超過は413、接続未設定は503です。

リポジトリのルートから、モデルを設定したバックエンドへ送る例:

```powershell
curl.exe http://localhost:8000/api/video-flow/verify --form "video=@docs/assets/video-demo/new-video-transfer/source.webm" --form "reference_json=<examples/new-video-handwashing-flow.json" --form "sample_interval_seconds=2"
```

`GET /api/video-flow/status`の`reference_ready`と`reference_reason`で接続状態を確認できます。
`GET /api/video-flow/reference-demo`は記録済みの工程判定、
`GET /api/video-flow/reference-demo/video`はその元動画を返します。

OpenAI接続は既存SDKの`responses.parse`とPydanticの出力モデルを使用します。
拒否や出力不足を成功結果へ変えず、工程・時刻の整合性はアプリでも検証します。
[公式の構造化出力ガイド](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)に照合しました。
Qwenは実画像をGPUへ渡し、厳密な整数フレームIDを元動画のサンプル時刻へ変換します。

## 今回の検証範囲

APIとプロバイダーの81件、MCPスクリプトの56件が通過しました。
新しいAPIのテストは、実動画をFFmpegでデコードして、明示した合成モデル回答で接続・検証処理を確認しています。
認識精度や、新しい動画への実OpenAI／Qwen推論を測ったものではありません。
今回、実APIキーでのOpenAI推論やQwenのモデル読み込みは実行していません。

Chromiumで、実MCP記録の読み込み、初回／最終の切り替え、引用時刻へのシーク、
デスクトップ／スマホ幅を確認しました。アップロードのブラウザテストでも実HTTPと動画デコードを使い、
合成回答で順序違反・引用なしの未確認・条件変更と失敗時の結果消去を確認しています。

```powershell
python -m pytest providers/tests backend/tests -q
python -m unittest discover -s scripts/tests
cd frontend
npm run typecheck
npm run build
```
