import type { VerificationReport } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

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
