// Mirrors the backend response schema (app/api/schemas.py).

export type StepStatus = "completed" | "not_done" | "unknown";

export interface StepResult {
  index: number;
  text: string;
  status: StepStatus;
  symbol: string;
  confidence: number;
  reason: string;
}

export interface Summary {
  total: number;
  completed: number;
  not_done: number;
  unknown: number;
}

export interface VerificationReport {
  provider: string;
  procedure_title: string;
  summary: Summary;
  steps: StepResult[];
}
