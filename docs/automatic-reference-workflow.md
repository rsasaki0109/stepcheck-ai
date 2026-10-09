# 初回判定と追加確認を1回の呼び出しで進める

`verify_reference_flow_auto`は、基準を1回渡すと、初回の画像判断から未確認箇所の追加確認まで進みます。
画像予算に合わせた間隔調整もサーバーが行い、追加確認は最大1回で終了します。
画像判断は接続した視覚対応ホストが行います。MCPサーバー自体がVLMになったわけではありません。

```python
verify_reference_flow_auto(
    reference=reference_json,
    sample_interval_seconds=2.0,
    refinement_interval_seconds=0.25,
    max_frames=24,
)
```

元動画はサーバーの`STEPCHECK_DEMO_VIDEO`で指定します。
保存先は`STEPCHECK_REFERENCE_REVIEW`です。別の出力先を使うと過去の試行を残せます。
`max_frames`は追加確認の画像予算です。初回は間隔を指定し、既存の上限96枚で検証します。

## 制御と終了条件

初回の画像を見たホストの回答について、工程ID、実画像の引用時刻、元動画ハッシュを検証します。
未確認がなければ追加の画像判断を省きます。工程がすべて観測されても順序違反がある場合は、その違反を保ちます。

未確認がある場合は、前後で観測した工程の引用時刻から探索範囲を作ります。
追加画像と比較用画像の全体が予算を超えると、間隔を2倍にして計画し直します。
この調整中は画像判断を要求しません。比較用画像を黙って捨てることもありません。
探索範囲は期待順序からのヒントであり、画面外や範囲外での動作を否定するものではありません。

間隔の試行は最大16回です。選んだ間隔で新しい画像がない、または予算に収められない場合は、
初回の未確認を保って終了します。計画に収まった場合だけ未確認の工程を再確認し、
その後も未確認なら`unknown_after_followup`として停止します。無限に再試行しません。

不正なJSON、今回渡していない時刻、既に確認した工程を書き換える回答はエラーです。
初回・追加確認の回答を検証し終えてから結果を保存し、エラーで以前の成功した結果を置き換えません。
最終結果には`workflow`としてsampling回数、停止理由、残った工程ID、間隔の調整履歴を保存します。

## 実動画で動かした結果

[別動画の確認](new-video-transfer.md)で使った32秒の映像を、今回は既知の動画として再度確認しました。
元動画のSHA-256は`8ad356691e9312a182d30a02dcffca118dbbc4c6480a4570b41b6ab662502332`です。
同じ5工程の基準を使い、**MCP Clientの`call_tool`を1回**呼んで、2つの画像判断へ進むことを確認しました。
これは自動制御の結合確認で、未知動画での新しい精度評価ではありません。

| 段階 | 実際の処理・結果 |
|---|---|
| 初回 | 2秒間隔＋終端付近の18枚を要求。Codexは4工程を観測、乾燥は未確認 |
| 自動計画 | 希望した0.25秒間隔は24枚の予算を超過。0.5秒へ自動調整 |
| 追加確認 | 12枚の新しい時刻＋3枚の比較用画像。乾燥のみをホストへ再確認 |
| 終了 | 乾燥が未確認のまま。全体の順序も`unknown`、停止理由は`unknown_after_followup` |

このセッションのCodexが両段階で**実際に出力された画像を表示して確認**し、新しいJSONを返しました。
以前の回答ファイルを使っていません。間隔変更と次のツール選択を人が挟む操作は不要でした。
前の4工程の理由・引用時刻・判断は変更せず、初回の結果も別ファイルに保存しました。
薄い泡の判断などの不確実性を残しています。独立した正解アノテーションや信頼度の測定ではありません。

- [1回の実ツール入力](assets/video-demo/automatic-reference-workflow/tool-request.json)
- [初回のプロンプトと画像ハッシュ](assets/video-demo/automatic-reference-workflow/pass-01/sampling-request.json)
- [初回画像1](assets/video-demo/automatic-reference-workflow/pass-01/sampling-0.png)、[画像2](assets/video-demo/automatic-reference-workflow/pass-01/sampling-1.png)、[今回の初回答](assets/video-demo/automatic-reference-workflow/pass-01/response.json)
- [追加確認のプロンプト](assets/video-demo/automatic-reference-workflow/pass-02/sampling-request.json)
- [追加画像1](assets/video-demo/automatic-reference-workflow/pass-02/sampling-0.png)、[画像2](assets/video-demo/automatic-reference-workflow/pass-02/sampling-1.png)、[今回の追加回答](assets/video-demo/automatic-reference-workflow/pass-02/response.json)
- [初回結果](assets/video-demo/automatic-reference-workflow/initial-verification.json)、[最終結果と調整履歴](assets/video-demo/automatic-reference-workflow/verification.json)
- [実MCP応答](assets/video-demo/automatic-reference-workflow/tool-result.json)、[元コード・画像・データのハッシュ](assets/video-demo/automatic-reference-workflow/manifest.json)

元映像と一覧画像は、Anthony Albright「Hand Washing」の[CC BY-SA 2.0](https://creativecommons.org/licenses/by-sa/2.0/)素材から生成しています。
[出典・変更内容](assets/video-demo/automatic-reference-workflow/ATTRIBUTION.md)を参照してください。

## 1コマンドで動かすアダプター

画像を見てファイルを書ける視覚対応セッション用です。新しい空のディレクトリを指定します。

```powershell
python scripts/run_flow_detection.py --video docs/assets/video-demo/new-video-transfer/source.webm --bridge-dir .tmp-flow-local/new-automatic-run --reference examples/new-video-handwashing-flow.json --interval 2 --auto-refine --output .tmp-flow-local/new-automatic-run/verification.json --reviewer "connected vision session" --source-credit "Anthony Albright / Hand Washing; CC BY-SA 2.0; https://commons.wikimedia.org/wiki/File:Hand_Washing_video.webm; Changes: timestamp sampling and resizing."
```

`pass-01`の実画像を確認して、その段階で求められたJSONを`pass-01/response.json`へ返します。
追加確認が必要なら自動で`pass-02`が現れ、実画像を見た回答を`pass-02/response.json`へ返します。
初回で未確認がない場合は`pass-02`を作りません。

**アダプターはモデルAPIを呼びません。画像を見るホストの回答は各段階で必要です。**
自動化したのはMCPの呼び出し制御・画像計画・追加確認への遷移・終了処理です。
通常の対応ホストならアダプターを使わず、同じツールの依存解決型samplingで回答できます。
[Webの工程確認](web-reference-verification.md)でも同じ画像計画・予算調整を使い、
OpenAIまたはローカルQwenへ初回と未確認の追加画像を渡せます。
Webはプロバイダーを直接呼び、MCPはsamplingホストが判断します。Webではこの実MCP記録の再生も可能です。

## ブラウザで根拠を確認する

成功した確認・追加確認のあと、アダプターは`--bridge-dir`へ`report.html`を自動出力します。
動画・引用時刻の縮小画像・実際の入力画像一覧を埋め込むので、HTML単体で開けます。
`--video`は環境変数より優先され、動画のハッシュもツール要求の記録に保存します。

- 1本の動画の4区間に近いレビュー画像と、元動画の再生
- 工程ごとの事前基準、判断理由、不確実性、引用時刻への移動
- 初回／最終結果の切り替え、順序チェックと残った未確認
- 追加確認の間隔調整と、SHA-256を照合した実MCP入力画像一覧

これは保存済みの視覚判断を確認する画面です。開くだけで新しい推論は行いません。
「未確認」を「未実施」や「完了」に変えず、色は工程の状態だけを表します。
ヒートマップ・アテンション・測定していない信頼度は表示しません。

前回の実MCP結果を使った[確認画面](assets/automatic-reference-report.html)も保存しました。
リポジトリを取得してこのファイルをブラウザで開いてください。GitHub上ではHTMLのソース表示になります。
保存版は元動画を相対パスで参照するため、`docs/assets`以下の配置を保つ必要があります。
派生画像のライセンスは元映像と同じCC BY-SA 2.0です。出典は画面の「元データと出典」に表示します。
[書き出したHTMLと元データのハッシュ](assets/automatic-reference-report-manifest.json)も保存しています。

推論をやり直さず、既存の結果から単独HTMLを作る場合:

```powershell
python scripts/render_reference_report.py --report docs/assets/video-demo/automatic-reference-workflow/verification.json --initial docs/assets/video-demo/automatic-reference-workflow/initial-verification.json --video docs/assets/video-demo/new-video-transfer/source.webm --bridge-dir docs/assets/video-demo/automatic-reference-workflow --output .tmp-flow-local/evidence-report.html --source-credit "Anthony Albright / Hand Washing; CC BY-SA 2.0; https://commons.wikimedia.org/wiki/File:Hand_Washing_video.webm; Changes: timestamp sampling and resizing."
```

`--linked-video`を付けると元動画だけを相対参照にし、HTMLの容量を減らせます。
別動画、未レビュー時刻の引用、記録と一致しない順序、初回結果の不一致、
別のMCP実行の画像や改変された入力画像はエラーとして拒否します。

## 検証

スクリプトのテスト56件が通過しました。自動制御の5件は実際のMCP依存解決の往復を使い、
2段階の回答、予算調整、未確認での終了、順序違反を保った追加確認の省略、不正な引用・JSONの拒否を確認しています。
テスト内の回答は合成fixtureで、VLMの認識精度を測るものではありません。
レポートの6件では元動画・引用・順序・初回・入力画像の整合性、HTMLへの文字列挿入の防止と、
実stdio経由での`--video`優先とHTML出力を確認しています。
Chromiumで元動画再生、工程選択とシーク、初回／最終切り替え、入力画像の表示、
デスクトップ／スマホ幅を確認し、JavaScriptエラーはありませんでした。

```powershell
python -m unittest discover -s scripts/tests
```
