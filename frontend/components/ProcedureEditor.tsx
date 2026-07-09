"use client";

interface Props {
  value: string;
  onChange: (value: string) => void;
}

export default function ProcedureEditor({ value, onChange }: Props) {
  return (
    <section className="flex h-full flex-col">
      <label
        htmlFor="procedure"
        className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-300"
      >
        Procedure (Markdown)
      </label>
      <textarea
        id="procedure"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
        className="h-full min-h-[300px] w-full flex-1 resize-none rounded-lg border border-slate-300 bg-white p-4 font-mono text-sm leading-relaxed text-slate-900 shadow-sm outline-none focus:border-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        placeholder={"# My procedure\n1. First step\n2. Second step"}
      />
    </section>
  );
}
