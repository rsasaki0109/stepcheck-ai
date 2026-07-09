"use client";

import type { VerificationReport } from "@/lib/types";
import StepCard from "./StepCard";

interface Props {
  report: VerificationReport | null;
  loading: boolean;
  error: string | null;
}

export default function ResultPanel({ report, loading, error }: Props) {
  if (loading) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-slate-500 dark:border-slate-800 dark:bg-slate-900">
        Analyzing images…
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
        {error}
      </div>
    );
  }

  if (!report) {
    return (
      <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-400 dark:border-slate-700">
        Results will appear here after you run a check.
      </div>
    );
  }

  const { summary } = report;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
          {report.procedure_title}
        </h2>
        <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          provider: {report.provider}
        </span>
        <div className="ml-auto flex gap-3 text-sm">
          <span className="text-completed">✅ {summary.completed}</span>
          <span className="text-notdone">❌ {summary.not_done}</span>
          <span className="text-unknown">⚠️ {summary.unknown}</span>
          <span className="text-slate-400">/ {summary.total}</span>
        </div>
      </div>

      <div className="grid gap-3">
        {report.steps.map((result) => (
          <StepCard key={result.index} result={result} />
        ))}
      </div>
    </div>
  );
}
