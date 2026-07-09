"use client";

import { useState } from "react";
import ImageUploader from "@/components/ImageUploader";
import ProcedureEditor from "@/components/ProcedureEditor";
import ResultPanel from "@/components/ResultPanel";
import { verifyProcedure } from "@/lib/api";
import type { VerificationReport } from "@/lib/types";

const SAMPLE = `# PC Assembly
1. Install the motherboard into the case
2. Mount the CPU
3. Attach the CPU cooler
4. Insert the memory modules
5. Connect the power cables`;

export default function Home() {
  const [procedure, setProcedure] = useState(SAMPLE);
  const [images, setImages] = useState<File[]>([]);
  const [report, setReport] = useState<VerificationReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canRun = procedure.trim().length > 0 && images.length > 0 && !loading;

  async function handleRun() {
    setLoading(true);
    setError(null);
    try {
      const result = await verifyProcedure(procedure, images);
      setReport(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setReport(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <header className="mb-8">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
          StepCheck AI
        </h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          AI-powered procedural verification from images.
        </p>
      </header>

      <div className="grid gap-6 md:grid-cols-2">
        <ProcedureEditor value={procedure} onChange={setProcedure} />
        <ImageUploader images={images} onChange={setImages} />
      </div>

      <div className="mt-6 flex items-center gap-3">
        <button
          type="button"
          onClick={handleRun}
          disabled={!canRun}
          className="rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-white"
        >
          {loading ? "Checking…" : "Run check"}
        </button>
        {images.length === 0 && (
          <span className="text-sm text-slate-400">
            Add at least one image to run a check.
          </span>
        )}
      </div>

      <div className="mt-8">
        <ResultPanel report={report} loading={loading} error={error} />
      </div>
    </main>
  );
}
