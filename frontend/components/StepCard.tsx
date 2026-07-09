"use client";

import type { StepResult, StepStatus } from "@/lib/types";

const STATUS_STYLES: Record<
  StepStatus,
  { label: string; badge: string; bar: string }
> = {
  completed: {
    label: "Completed",
    badge: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300",
    bar: "bg-green-500",
  },
  not_done: {
    label: "Not done",
    badge: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
    bar: "bg-red-500",
  },
  unknown: {
    label: "Undetermined",
    badge: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
    bar: "bg-amber-500",
  },
};

export default function StepCard({ result }: { result: StepResult }) {
  const style = STATUS_STYLES[result.status];
  const confidencePct = Math.round(result.confidence * 100);

  return (
    <article className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
            Step {result.index}
          </p>
          <p className="mt-0.5 font-medium text-slate-900 dark:text-slate-100">
            {result.text}
          </p>
        </div>
        <span
          className={`shrink-0 rounded-full px-3 py-1 text-xs font-semibold ${style.badge}`}
        >
          {result.symbol} {style.label}
        </span>
      </div>

      <div className="mt-3">
        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>Confidence</span>
          <span>{confidencePct}%</span>
        </div>
        <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
          <div
            className={`h-full rounded-full ${style.bar}`}
            style={{ width: `${confidencePct}%` }}
          />
        </div>
      </div>

      <p className="mt-3 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
        <span className="font-semibold text-slate-700 dark:text-slate-200">
          Reason:{" "}
        </span>
        {result.reason}
      </p>
    </article>
  );
}
