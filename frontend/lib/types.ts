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
  reference_ready: boolean;
  reference_reason: string | null;
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

export interface ReferenceFlow {
  title: string;
  scope?: string;
  steps: { id: string; label: string; criterion: string }[];
}

export interface ReferenceStepResult {
  step_id: string;
  index: number;
  label: string;
  status: "observed" | "unknown";
  reason: string;
  uncertainty: string;
  evidence_seconds: number[];
}

export interface ReferencePass {
  steps: ReferenceStepResult[];
  transitions: { from: string; to: string; status: "sampled_before" | "unknown" | "violated" }[];
  order_status: "supported_sample_order" | "unknown" | "violated";
  sampled_seconds?: number[] | null;
}

export interface VideoReferenceReport extends ReferencePass {
  title: string;
  reference: ReferenceFlow;
  provider: string;
  model: string;
  analysis_mode: "live" | "recorded_demo";
  source_sha256: string;
  duration_seconds: number;
  sample_interval_seconds: number | null;
  expected_procedure_supplied: true;
  sampled_seconds: number[];
  frames: VideoFrame[];
  time_note: string;
  scope_note: string;
  initial: ReferencePass | null;
  workflow: { sampling_requests: number; stop_reason: string; unknown_step_ids: string[];
    interval_selection?: { chosen_interval_seconds: number | null;
      attempts: { interval_seconds: number; status: string; frames?: number }[] } | null } | null;
  source_credit: string | null;
  refinement?: { target_step_ids: string[]; sampled_seconds: number[]; added_seconds: number[];
    windows: { step_id: string; start_seconds: number; end_seconds: number }[]; selection_note: string } | null;
}
