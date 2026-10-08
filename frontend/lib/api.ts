import type { VerificationReport, VideoFlowReport, VideoFlowStatus } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function readResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((item: { msg: string }) => item.msg).join("; ");
    } catch { /* retain status */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const demoVideoUrl = `${API_BASE}/api/video-flow/demo/video`;

export async function getVideoFlowStatus(signal?: AbortSignal): Promise<VideoFlowStatus> {
  return readResponse(await fetch(`${API_BASE}/api/video-flow/status`, { signal }));
}

export async function detectVideoFlow(video: File, interval: number, signal?: AbortSignal): Promise<VideoFlowReport> {
  const form = new FormData();
  form.append("video", video);
  form.append("sample_interval_seconds", String(interval));
  return readResponse(await fetch(`${API_BASE}/api/video-flow`, { method: "POST", body: form, signal }));
}

export async function getRecordedDemo(signal?: AbortSignal): Promise<VideoFlowReport> {
  return readResponse(await fetch(`${API_BASE}/api/video-flow/demo`, { signal }));
}

export async function verifyProcedure(
  procedure: string,
  images: File[],
): Promise<VerificationReport> {
  const form = new FormData();
  form.append("procedure", procedure);
  for (const image of images) {
    form.append("images", image);
  }

  const response = await fetch(`${API_BASE}/api/verify`, {
    method: "POST",
    body: form,
  });

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* keep default */
    }
    throw new Error(detail);
  }

  return (await response.json()) as VerificationReport;
}
