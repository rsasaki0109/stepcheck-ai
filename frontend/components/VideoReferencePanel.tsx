"use client";

import { useEffect, useRef, useState } from "react";
import { getReferenceDemo, getVideoFlowStatus, referenceDemoVideoUrl, verifyVideoReference } from "@/lib/api";
import type { ReferenceFlow, ReferenceStepResult, VideoFlowStatus, VideoReferenceReport } from "@/lib/types";

const card = "rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900";
const muted = "text-slate-500 dark:text-slate-400";
const input = "w-full min-w-0 rounded-lg border border-slate-300 bg-transparent px-3 py-2 text-sm dark:border-slate-700";
const button = "rounded-lg border border-slate-300 px-3 py-2 text-sm disabled:opacity-40 dark:border-slate-700";
const seconds = (t: number) => `${Number(t.toFixed(3))}s`;
const orderText = { supported_sample_order: "引用画像の順序を支持", unknown: "未確認", violated: "引用画像の順序に違反" };
const edgeText = { sampled_before: "引用画像ではこの順序", unknown: "順序は未確認", violated: "順序に違反" };
const sampleReference: ReferenceFlow = { title: "映像で確認する手洗いの流れ", steps: [
  { id: "wet", label: "手を水で濡らす", criterion: "泡立てる前に、水が手に当たる。蛇口が近くにあるだけでは不十分。" },
  { id: "soap", label: "石けんを手につける", criterion: "容器や固形石けんから手に石けんをつける様子が見える。泡だけでは判定しない。" },
  { id: "lather", label: "泡をつけて手をこする", criterion: "石けんの泡が見え、両手をこすり合わせる。泡が不明瞭なら未確認。" },
  { id: "rinse", label: "手を水ですすぐ", criterion: "泡をつけてこすった後に、水が手に当たる。蛇口の近くでこするだけでは不十分。" },
  { id: "dry", label: "手を乾かす", criterion: "紙・タオルが手に当たって拭く、または作動している乾燥機に手を入れる。画面外なら未確認。" },
] };

export default function VideoReferencePanel() {
  const [status, setStatus] = useState<VideoFlowStatus | null>(null);
  const [reference, setReference] = useState<ReferenceFlow>(sampleReference);
  const [file, setFile] = useState<File | null>(null);
  const [localUrl, setLocalUrl] = useState("");
  const [demoLoaded, setDemoLoaded] = useState(false);
  const [interval, setInterval] = useState(2);
  const [report, setReport] = useState<VideoReferenceReport | null>(null);
  const [pass, setPass] = useState<"initial" | "final">("final");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [evidenceTime, setEvidenceTime] = useState<number | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const video = useRef<HTMLVideoElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const request = useRef<AbortController | null>(null);
  const pendingTime = useRef<number | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getVideoFlowStatus(controller.signal).then(setStatus).catch((err) => {
      if (err.name !== "AbortError") setError("バックエンドに接続できません。");
    });
    return () => { controller.abort(); request.current?.abort(); };
  }, []);
  useEffect(() => {
    if (!file) { setLocalUrl(""); return; }
    const url = URL.createObjectURL(file);
    setLocalUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function clearResult() {
    setReport(null); setDemoLoaded(false); setSelectedId(null); setEvidenceTime(null);
    setCurrentTime(0); pendingTime.current = null; setError(null);
  }
  function edit(next: ReferenceFlow) { clearResult(); setReference(next); }
  function chooseFile(next: File | null) {
    clearResult();
    if (next && next.size > (status?.max_video_bytes ?? 50 * 1024 * 1024)) {
      setFile(null); setError("動画の容量が上限を超えています。");
      if (fileInput.current) fileInput.current.value = "";
    } else setFile(next);
  }
  function seek(t: number) {
    pendingTime.current = t;
    if (video.current) {
      video.current.pause();
      if (video.current.readyState >= 1) { video.current.currentTime = t; pendingTime.current = null; }
    }
    setCurrentTime(t);
  }
  function select(step: ReferenceStepResult) {
    setSelectedId(step.step_id);
    setEvidenceTime(step.evidence_seconds[0] ?? null);
    if (step.evidence_seconds.length) seek(step.evidence_seconds[0]);
    else { video.current?.pause(); pendingTime.current = null; }
  }
  function move(index: number, delta: number) {
    const steps = [...reference.steps];
    [steps[index], steps[index + delta]] = [steps[index + delta], steps[index]];
    edit({ ...reference, steps });
  }
  async function run(demo: boolean) {
    if (!demo && !file) return;
    const controller = new AbortController(); request.current = controller;
    clearResult(); setLoading(true); setPass("final");
    try {
      const result = demo ? await getReferenceDemo(controller.signal) : await verifyVideoReference(file!, reference, interval, controller.signal);
      if (controller.signal.aborted) return;
      if (demo) { setFile(null); setDemoLoaded(true); setReference(result.reference); if (fileInput.current) fileInput.current.value = ""; }
      setReport(result);
      if (result.steps[0]) {
        select(result.steps[0]);
        // A demo replaces the mounted source video after this state update.
        if (demo) pendingTime.current = result.steps[0].evidence_seconds[0] ?? null;
      }
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "確認に失敗しました。");
    } finally { if (!controller.signal.aborted) setLoading(false); }
  }

  const displayed = pass === "initial" && report?.initial ? report.initial : report;
  const selected = displayed?.steps.find(s => s.step_id === selectedId);
  const evidence = report?.frames.find(f => f.timestamp_seconds === evidenceTime);
  const sourceUrl = demoLoaded ? referenceDemoVideoUrl : localUrl;
  const valid = reference.title.trim() && reference.steps.length > 0 && reference.steps.every(s => s.label.trim());
  const canRun = Boolean(file && valid && status?.reference_ready && !loading && Number.isFinite(interval) && interval >= 0.25 && interval <= 30);
  const quarters = report ? Array.from({ length: 4 }, (_, i) => {
    const target = report.duration_seconds * i / 4;
    return report.frames.reduce((a, b) => Math.abs(a.timestamp_seconds - target) <= Math.abs(b.timestamp_seconds - target) ? a : b);
  }) : [];

  return <section aria-label="動画で工程の順序を確認">
    <fieldset disabled={loading} className={`${card} min-w-0`}>
      <h2 className="text-xl font-semibold">1本の動画で、工程と順序を確認する</h2>
      <p className={`mt-2 text-sm ${muted}`}>先に確認したい工程を並べます。映像の根拠が足りなければ未確認のまま残します。</p>
      <label className="mt-5 block text-sm">フローの名前<input className={`${input} mt-1`} value={reference.title} maxLength={100} onChange={e => edit({ ...reference, title: e.target.value })} /></label>
      <details open={!report} className="mt-4"><summary className="cursor-pointer text-sm font-semibold">確認する {reference.steps.length} 工程 · 順番と条件を編集</summary>
      <ol className="mt-4 space-y-3" aria-label="確認する工程の基準">
        {reference.steps.map((step, i) => <li key={step.id} className="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
          <div className="flex flex-wrap items-center gap-2"><span className="text-sm font-semibold">工程 {i + 1}</span>
            <button className={button} type="button" disabled={i === 0} aria-label={`工程 ${i + 1} を上へ`} onClick={() => move(i, -1)}>↑</button>
            <button className={button} type="button" disabled={i === reference.steps.length - 1} aria-label={`工程 ${i + 1} を下へ`} onClick={() => move(i, 1)}>↓</button>
            <button className={`${button} ml-auto`} type="button" disabled={reference.steps.length <= 1} onClick={() => edit({ ...reference, steps: reference.steps.filter(s => s.id !== step.id) })}>削除</button></div>
          <label className="mt-2 block text-xs">工程名<input className={`${input} mt-1`} value={step.label} maxLength={160} onChange={e => edit({ ...reference, steps: reference.steps.map(s => s.id === step.id ? { ...s, label: e.target.value } : s) })} /></label>
          <div className="mt-2"><label htmlFor={`criterion-${step.id}`} className="block text-xs">何が見えれば確認できるか</label><textarea id={`criterion-${step.id}`} className={`${input} mt-1`} rows={2} value={step.criterion} maxLength={2000} onChange={e => edit({ ...reference, steps: reference.steps.map(s => s.id === step.id ? { ...s, criterion: e.target.value } : s) })} /></div>
        </li>)}
      </ol>
      <button className={`${button} mt-3`} type="button" disabled={reference.steps.length >= 30} onClick={() => edit({ ...reference, steps: [...reference.steps, { id: crypto.randomUUID(), label: "", criterion: "" }] })}>工程を追加</button>
      </details>
      <div className="mt-5 flex flex-wrap items-end gap-4">
        <label className="min-w-0 flex-1 text-sm">元動画<input ref={fileInput} type="file" accept="video/*" className="mt-2 block w-full min-w-0 text-sm" onChange={e => chooseFile(e.target.files?.[0] ?? null)} /></label>
        <label className="text-sm">画像の間隔（秒）<input type="number" min={0.25} max={30} step={0.25} value={interval} onChange={e => { clearResult(); setInterval(Number(e.target.value)); }} className={`${input} mt-1 max-w-32`} /></label>
      </div>
      <div className="mt-5 flex flex-wrap gap-3"><button type="button" disabled={!canRun} onClick={() => run(false)} className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">{loading ? "確認中…" : "この動画で工程を確認"}</button>
        <button type="button" className={button} onClick={() => run(true)}>記録済みの工程確認を見る</button></div>
      {!status?.reference_ready && <p className={`mt-3 text-sm ${muted}`}>{status?.reference_reason || "モデル接続を確認しています。"} 記録済み結果は接続キーなしで見られます。</p>}
      <p className={`mt-3 text-xs ${muted}`}>アップロードの確認は初回の画像判断を行います。記録済み結果では、前回の追加確認も比較できます。</p>
    </fieldset>
    {error && <p role="alert" className="mt-4 rounded-lg bg-red-50 p-4 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">{error}</p>}
    {report && <section className={`${card} mt-6`} aria-label="動画の4区間"><h3 className="font-semibold">動画の4区間</h3>
      <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">{quarters.map((f, i) => <button key={i} type="button" onClick={() => seek(f.timestamp_seconds)} className="min-w-0 rounded-lg border border-slate-200 p-2 text-left dark:border-slate-700">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={f.image_url} alt={`区間 ${i + 1} のレビュー画像 ${seconds(f.timestamp_seconds)}`} className="aspect-video w-full rounded bg-slate-950 object-contain" /><span className={`mt-2 block text-xs ${muted}`}>{i + 1} / {seconds(f.timestamp_seconds)}</span></button>)}</div>
      <p className={`mt-3 text-xs ${muted}`}>各区間の開始に近いレビュー画像です。クリックすると元動画へ移動します。</p></section>}
    <div className="mt-6 grid gap-6 md:grid-cols-2">
      <section className={`${card} min-w-0`}><h3 className="font-semibold">元動画</h3>
        {sourceUrl ? <video key={sourceUrl} ref={video} src={sourceUrl} controls playsInline preload="metadata" className="mt-3 aspect-video w-full rounded-xl bg-slate-950 object-contain"
          onLoadedMetadata={() => { if (pendingTime.current !== null && video.current) { video.current.currentTime = pendingTime.current; pendingTime.current = null; } }}
          onTimeUpdate={() => setCurrentTime(video.current?.currentTime ?? 0)} onError={() => setError("ブラウザで動画を再生できません。引用画像で確認できます。")} />
          : <p className={`py-12 text-center text-sm ${muted}`}>動画を選ぶか、記録済み結果を開いてください。</p>}
        <p className={`mt-3 text-xs ${muted}`}>{seconds(currentTime)} · {demoLoaded ? "記録済み結果の元動画" : file?.name}</p>
      </section>
      <section className={`${card} min-w-0`} aria-label="工程の判定結果"><h3 className="font-semibold">工程と順序</h3>
        {report && displayed ? <>
          <p className={`mt-2 text-xs ${report.analysis_mode === "recorded_demo" ? "text-amber-700 dark:text-amber-300" : "text-teal-700 dark:text-teal-300"}`}>{report.analysis_mode === "recorded_demo" ? "記録済みのCodex MCP判断・再解析なし" : "今回の動画へのモデル判断・根拠の確認が必要"}</p>
          {report.initial && <label className="mt-3 block text-sm">表示する判定<select className={`${input} mt-1`} value={pass} onChange={e => { const next = e.target.value as "initial" | "final"; setPass(next); const result = next === "initial" ? report.initial! : report; select(result.steps.find(s => s.step_id === selectedId) ?? result.steps[0]); }}><option value="final">最終結果</option><option value="initial">初回</option></select></label>}
          <p className={`mt-3 text-sm font-semibold ${displayed.order_status === "supported_sample_order" ? "text-teal-700 dark:text-teal-300" : displayed.order_status === "violated" ? "text-red-700 dark:text-red-300" : "text-amber-700 dark:text-amber-300"}`}>全体の順序: {orderText[displayed.order_status]}</p>
          <ol className="mt-3 space-y-2">{displayed.steps.map((s, i) => <li key={s.step_id}>{i > 0 && <p className={`mb-2 pl-3 text-xs ${muted}`}>↓ {edgeText[displayed.transitions[i - 1].status]}</p>}
            <button type="button" aria-pressed={selectedId === s.step_id} onClick={() => select(s)} className={`w-full rounded-lg border p-3 text-left text-sm ${selectedId === s.step_id ? "border-teal-500 bg-teal-50 dark:bg-teal-950/40" : "border-slate-200 dark:border-slate-700"}`}>
              {s.index}. {s.label} <span className={s.status === "observed" ? "text-teal-700 dark:text-teal-300" : "text-amber-700 dark:text-amber-300"}>/ {s.status === "observed" ? "観測あり" : "未確認"}</span></button></li>)}</ol>
          <p className={`mt-3 text-xs ${muted}`}>引用画像の順序で確認します。連続した実行や全工程の完了を保証しません。</p>
        </> : <p className={`py-12 text-center text-sm ${muted}`}>各工程の判定と順序がここに並びます。</p>}
      </section>
    </div>
    {report && selected && <section className={`${card} mt-6`} aria-label="工程の引用画像"><h3 className="font-semibold">{selected.index}. {selected.label} の根拠</h3>
      <div className="mt-4 grid min-w-0 gap-6 md:grid-cols-2"><div className="min-w-0">
        {evidence ? <>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={evidence.image_url} alt={`${selected.label} の引用画像 ${seconds(evidence.timestamp_seconds)}`} className="aspect-video w-full rounded-xl bg-slate-950 object-contain" />
        </> : <p className={`py-12 text-center text-sm ${muted}`}>引用画像はありません。</p>}
        <div className="mt-3 flex flex-wrap gap-2">{selected.evidence_seconds.map(t => <button type="button" key={t} className={`${button} ${t === evidenceTime ? "border-teal-500 text-teal-700 dark:text-teal-300" : ""}`} aria-pressed={t === evidenceTime} onClick={() => { setEvidenceTime(t); seek(t); }}>{seconds(t)}</button>)}</div></div>
        <div className="min-w-0 text-sm leading-relaxed">{selected.status === "unknown" && <p className="text-amber-700 dark:text-amber-300">未確認は「実施していない」という判定ではありません。</p>}
          <h4 className="mt-3 font-semibold">事前に与えた基準</h4><p className={`mt-1 ${muted}`}>{report.reference.steps.find(s => s.id === selected.step_id)?.criterion || "工程名を基準に確認しています。"}</p>
          <h4 className="mt-4 font-semibold">判断理由</h4><p className={`mt-1 ${muted}`}>{selected.reason}</p>
          <h4 className="mt-4 font-semibold">不確実性</h4><p className={`mt-1 ${muted}`}>{selected.uncertainty || "個別の不確実性は報告されていません。"}</p>
          <p className={`mt-4 text-xs ${muted}`}>元動画の引用時刻の画像です。ヒートマップや測定した信頼度ではありません。</p></div></div>
    </section>}
    {report && <details className={`${card} mt-6`}><summary className="cursor-pointer text-sm font-semibold">解析範囲・追加確認・出典</summary>
      <p className={`mt-3 text-sm ${muted}`}>{report.scope_note}</p>
      {report.workflow && <><p className={`mt-3 text-sm ${muted}`}>記録上の画像判断: {report.workflow.sampling_requests}回 · 未確認: {report.workflow.unknown_step_ids.join(", ") || "なし"}</p>
        {report.workflow.interval_selection?.attempts.map((a, i) => <p key={i} className={`mt-1 text-xs ${muted}`}>{seconds(a.interval_seconds)} 間隔: {a.status === "over_budget" ? "画像予算を超過" : a.status === "fits" ? `${a.frames}枚で予算内` : a.status}</p>)}</>}
      {!report.workflow && <p className={`mt-3 text-sm ${muted}`}>今回のWeb確認は初回の判断です。追加確認は実行していません。</p>}
      {report.source_credit && <p className={`mt-3 break-words text-xs ${muted}`}>{report.source_credit}</p>}
      <p className={`mt-3 break-all text-xs ${muted}`}>{report.provider} / {report.model} · {report.frames.length}枚 · 動画SHA-256: {report.source_sha256}</p></details>}
  </section>;
}
