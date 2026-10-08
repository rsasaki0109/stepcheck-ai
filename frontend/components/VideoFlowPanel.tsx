"use client";

import { useEffect, useRef, useState } from "react";
import { demoVideoUrl, detectVideoFlow, getRecordedDemo, getVideoFlowStatus } from "@/lib/api";
import type { VideoAction, VideoFlowReport, VideoFlowStatus } from "@/lib/types";

const card = "rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900";
const muted = "text-slate-500 dark:text-slate-400";
const seconds = (value: number) => `${Number(value.toFixed(3))}s`;

export default function VideoFlowPanel() {
  const [status, setStatus] = useState<VideoFlowStatus | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [localUrl, setLocalUrl] = useState("");
  const [demoLoaded, setDemoLoaded] = useState(false);
  const [interval, setInterval] = useState(0.75);
  const [report, setReport] = useState<VideoFlowReport | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [evidenceTime, setEvidenceTime] = useState<number | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [loading, setLoading] = useState<"live" | "demo" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const requestRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getVideoFlowStatus(controller.signal).then(setStatus).catch((err) => {
      if (err.name !== "AbortError") setError("APIに接続できません。バックエンドの起動を確認してください。");
    });
    return () => { controller.abort(); requestRef.current?.abort(); };
  }, []);

  useEffect(() => {
    if (!file) { setLocalUrl(""); return; }
    const url = URL.createObjectURL(file);
    setLocalUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function chooseFile(next: File | null) {
    setError(null);
    setReport(null);
    setSelectedId(null);
    setEvidenceTime(null);
    setDemoLoaded(false);
    setCurrentTime(0);
    if (next && next.size > (status?.max_video_bytes ?? 50 * 1024 * 1024)) {
      setFile(null);
      setError("動画の容量が上限を超えています。");
      if (fileRef.current) fileRef.current.value = "";
      return;
    }
    setFile(next);
  }

  function seek(timestamp: number) {
    setEvidenceTime(timestamp);
    if (videoRef.current) {
      videoRef.current.pause();
      videoRef.current.currentTime = timestamp;
    }
    setCurrentTime(timestamp);
  }

  function selectAction(action: VideoAction) {
    setSelectedId(action.id);
    seek(action.evidence_seconds[0]);
  }

  async function run(mode: "live" | "demo") {
    if (mode === "live" && !file) return;
    const controller = new AbortController();
    requestRef.current = controller;
    setLoading(mode);
    setError(null);
    setReport(null);
    setSelectedId(null);
    setEvidenceTime(null);
    try {
      const result = mode === "demo" ? await getRecordedDemo(controller.signal) : await detectVideoFlow(file!, interval, controller.signal);
      if (controller.signal.aborted) return;
      if (mode === "demo") {
        setFile(null);
        setDemoLoaded(true);
        if (fileRef.current) fileRef.current.value = "";
      }
      setReport(result);
      setSelectedId(result.actions[0]?.id ?? null);
      setEvidenceTime(result.actions[0]?.evidence_seconds[0] ?? null);
      if (mode === "live" && result.actions[0]) seek(result.actions[0].evidence_seconds[0]);
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "解析に失敗しました。");
    } finally {
      if (!controller.signal.aborted) setLoading(null);
    }
  }

  const selected = report?.actions.find((action) => action.id === selectedId);
  const evidence = report?.frames.find((frame) => frame.timestamp_seconds === evidenceTime);
  const sourceUrl = demoLoaded ? demoVideoUrl : localUrl;
  const canRun = Boolean(file && status?.ready && !loading && Number.isFinite(interval) && interval >= 0.25 && interval <= 30);

  return (
    <section aria-label="動画からフローを検出">
      <div className={`${card} p-5 md:p-6`}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold">1本の動画から、作業のフローを見つける</h2>
            <p className={`mt-2 text-sm ${muted}`}>手順書は不要です。見えた動作を順番に並べ、根拠の場面を確認できます。</p>
          </div>
          <span className="rounded-full bg-teal-50 px-3 py-1 text-xs font-medium text-teal-700 dark:bg-teal-950 dark:text-teal-300">動画 → 動作 → 根拠</span>
        </div>
        <div className="mt-6 flex flex-wrap items-end gap-4">
          <label className="min-w-0 flex-1 text-sm font-medium">
            動画ファイル
            <input ref={fileRef} type="file" accept="video/*,.mp4,.webm,.mov,.mkv" disabled={Boolean(loading)}
              onChange={(event) => chooseFile(event.target.files?.[0] ?? null)}
              className="mt-2 block w-full rounded-lg border border-slate-300 p-2 text-sm file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-2 dark:border-slate-700 dark:file:bg-slate-800 dark:file:text-slate-100" />
          </label>
          <label className="text-sm font-medium">
            フレームの間隔（秒）
            <input type="number" min={0.25} max={30} step={0.25} value={interval} disabled={Boolean(loading)}
              onChange={(event) => setInterval(Number(event.target.value))}
              className="mt-2 block w-36 rounded-lg border border-slate-300 bg-transparent px-3 py-3 dark:border-slate-700" />
          </label>
          <button type="button" onClick={() => run("live")} disabled={!canRun}
            className="rounded-lg bg-teal-700 px-5 py-3 text-sm font-semibold text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-40">
            {loading === "live" ? "動画を解析中…" : "フローを検出"}
          </button>
          <button type="button" onClick={() => run("demo")} disabled={Boolean(loading)}
            className="rounded-lg border border-slate-300 px-4 py-3 text-sm font-medium hover:bg-slate-100 disabled:opacity-40 dark:border-slate-700 dark:hover:bg-slate-800">
            {loading === "demo" ? "デモを読み込み中…" : "記録済みデモを見る"}
          </button>
        </div>
        <p className={`mt-3 text-xs ${muted}`}>
          最大 {Math.round((status?.max_video_bytes ?? 50 * 1024 * 1024) / 1024 / 1024)} MB / {status?.max_video_seconds ?? 120} 秒。長い動画では間隔を広げて全体から抽出します。
        </p>
        {status && !status.ready && <p role="status" className="mt-3 text-sm text-amber-700 dark:text-amber-300">{status.reason} 記録済みデモはキーなしで確認できます。</p>}
        {status?.ready && <p className={`mt-3 text-xs ${muted}`}>
          {status.provider === "qwen-local" ? "動画から抽出したフレームを、この実行環境のローカルVLMで解析します。初回はモデルのダウンロードと読み込みに時間がかかります。" : "解析には動画から抽出したフレームをOpenAIに送信します。"}
        </p>}
      </div>

      {error && <div role="alert" className="mt-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">{error}</div>}
      {loading && <div role="status" aria-live="polite" className={`mt-4 ${card} p-5 text-sm ${muted}`}>
        {loading === "live" ? "動画からフレームを抽出し、見えた動作と根拠を解析しています。" : "保存済みの認識結果と、元動画の根拠フレームを読み込んでいます。"}
      </div>}

      <div className="mt-6 grid items-start gap-6 lg:grid-cols-[1fr_1fr]">
        <div className={`${card} min-w-0 overflow-hidden`}>
          <div className="flex items-center justify-between gap-3 px-5 py-4">
            <h3 className="font-semibold">元の動画</h3>
            <span className={`text-xs ${muted}`}>{seconds(currentTime)}</span>
          </div>
          {sourceUrl ? <video ref={videoRef} key={sourceUrl} src={sourceUrl} controls playsInline preload="metadata"
            aria-label={demoLoaded ? "記録済みデモの手洗い動画" : "アップロードした動画"}
            onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
            onLoadedMetadata={() => { if (evidenceTime !== null) seek(evidenceTime); }}
            onError={() => setError("このブラウザーでは動画を再生できません。解析後は抽出した根拠画像で確認できます。")}
            className="aspect-video w-full bg-slate-950 object-contain" />
            : <div className={`flex aspect-video items-center justify-center bg-slate-100 p-6 text-sm dark:bg-slate-950 ${muted}`}>動画を選ぶか、記録済みデモを開いてください。</div>}
          <p className={`px-5 py-4 text-xs ${muted}`}>{demoLoaded ? "CDCの手洗い動画。記録済みのCodex認識を表示しています。" : file?.name ?? "フローの動作を選ぶと、根拠時刻に移動します。"}</p>
        </div>

        <div className={`${card} min-w-0 p-5`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-semibold">検出したフロー</h3>
            {report && <span className={`rounded-full px-3 py-1 text-xs ${report.analysis_mode === "recorded_demo" ? "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300" : "bg-teal-50 text-teal-700 dark:bg-teal-950 dark:text-teal-300"}`}>{report.analysis_mode === "recorded_demo" ? "記録済みデモ・再解析なし" : "今回の動画の解析結果"}</span>}
          </div>
          {!report ? <p className={`py-12 text-center text-sm ${muted}`}>解析すると、見えた動作がここに並びます。</p>
            : <>
              <p className={`mt-2 text-sm ${muted}`}>{report.title} · {report.actions.length} 動作 · {report.frames.length} フレーム</p>
              {report.actions.length === 0 && <p className="mt-4 text-sm text-amber-700 dark:text-amber-300">動作を特定できませんでした。下の不明点を確認してください。</p>}
              <ol className="mt-4 max-h-[420px] space-y-2 overflow-y-auto pr-1">
                {report.actions.map((action, index) => (
                  <li key={action.id}>
                    {index > 0 && <p className={`mb-2 pl-5 text-xs ${muted}`}>
                      {report.transitions[index - 1]?.status === "ambiguous" ? "↓ 順番は不明（根拠時刻が重複）" : "↓ 根拠フレームの順番"}
                    </p>}
                    <button type="button" aria-pressed={selectedId === action.id} onClick={() => selectAction(action)}
                      className={`flex w-full items-start gap-3 rounded-xl border p-3 text-left transition ${selectedId === action.id ? "border-teal-500 bg-teal-50 dark:bg-teal-950/40" : "border-slate-200 hover:border-teal-400 dark:border-slate-700"}`}>
                      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold dark:bg-slate-800">{action.id}</span>
                      <span className="min-w-0 flex-1"><span className="block text-sm font-medium">{action.label}</span>
                        <span className={`mt-1 block text-xs ${muted}`}>{seconds(action.first_seen_seconds)}–{seconds(action.last_seen_seconds)} · {action.evidence_seconds.length} 枚の根拠</span>
                        {action.uncertainty && <span className="mt-1 block text-xs text-amber-700 dark:text-amber-300">解釈に不明点あり</span>}
                      </span>
                    </button>
                  </li>
                ))}
              </ol>
              <p className={`mt-4 text-xs ${muted}`}>時刻は確認できたフレームを示します。動作の開始・終了時刻や、手順全体の正しさを保証するものではありません。</p>
            </>}
        </div>
      </div>

      {selected && <section className={`mt-6 ${card} p-5 md:p-6`} aria-label="選択した動作の根拠">
        <h3 className="text-lg font-semibold">{selected.id}. {selected.label} の根拠</h3>
        <div className="mt-4 grid gap-6 md:grid-cols-2">
          <div>
            {evidence && (
              // Native data URLs contain the exact server-decoded supporting frame.
              // eslint-disable-next-line @next/next/no-img-element
              <img src={evidence.image_url} alt={`${selected.label}の根拠フレーム ${seconds(evidence.timestamp_seconds)}`} className="aspect-video w-full rounded-xl bg-slate-950 object-contain" />
            )}
            <div className="mt-3 flex flex-wrap gap-2" aria-label="根拠フレームの時刻">
              {selected.evidence_seconds.map((timestamp) => <button type="button" key={timestamp} onClick={() => seek(timestamp)} aria-pressed={timestamp === evidenceTime}
                className={`rounded-lg border px-3 py-2 text-xs ${timestamp === evidenceTime ? "border-teal-500 bg-teal-50 text-teal-800 dark:bg-teal-950 dark:text-teal-200" : "border-slate-300 dark:border-slate-700"}`}>{seconds(timestamp)}</button>)}
            </div>
          </div>
          <div className="text-sm leading-relaxed">
            <h4 className="font-semibold">見えたこと</h4><p className={`mt-2 ${muted}`}>{selected.reason}</p>
            {selected.uncertainty && <><h4 className="mt-5 font-semibold text-amber-700 dark:text-amber-300">不明なこと</h4><p className={`mt-2 ${muted}`}>{selected.uncertainty}</p></>}
            <p className={`mt-5 text-xs ${muted}`}>画像は元動画から抽出したフレームです。</p>
          </div>
        </div>
      </section>}

      {report && <details className={`mt-6 ${card} p-5`}>
        <summary className="cursor-pointer text-sm font-semibold">解析範囲と不明点</summary>
        <ul className={`mt-3 list-disc space-y-2 pl-5 text-sm ${muted}`}>
          {report.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}
        </ul>
        <p className={`mt-4 break-all text-xs ${muted}`}>認識: {report.provider} / {report.model} · フレーム間隔: 約 {seconds(report.sample_interval_seconds)} · 動画: {seconds(report.duration_seconds)}</p>
      </details>}
    </section>
  );
}
