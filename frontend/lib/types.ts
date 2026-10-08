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

export interface VideoFlowStatus {
  ready: boolean;
  provider: string;
  model: string;
  reason: string | null;
  max_video_bytes: number;
  max_video_seconds: number;
  max_video_frames: number;
}

export interface VideoAction {
  id: number;
  label: string;
  reason: string;
  uncertainty: string;
  evidence_seconds: number[];
  first_seen_seconds: number;
  last_seen_seconds: number;
}

export interface VideoFrame {
  timestamp_seconds: number;
  image_url: string;
}

export interface VideoFlowReport {
  title: string;
  provider: string;
  model: string;
  analysis_mode: "live" | "recorded_demo";
  source_sha256: string;
  duration_seconds: number;
  sample_interval_seconds: number;
  expected_procedure_supplied: boolean;
  actions: VideoAction[];
  transitions: { from: number; to: number; status: "sampled_before" | "ambiguous"; reason: string }[];
  sampled_seconds: number[];
  frames: VideoFrame[];
  limitations: string[];
  time_note: string;
}
