import type { CoverLetterTone, Intensity, PageTarget, ParsedResume, Resume, Section, TailorResult } from "./types";

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {}

async function errorFrom(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return new ApiError(body.detail);
  } catch {
    /* non-JSON error body */
  }
  if (res.status === 429) return new ApiError("Too many requests. Please wait a moment and try again.");
  if (res.status >= 500) return new ApiError("The server ran into a problem. Please try again shortly.");
  return new ApiError(`Request failed (${res.status}).`);
}

async function request(path: string, init: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(
      "Can't reach the server. Check your connection — if the API was idle it may take ~30s to wake up, so try again.",
    );
  }
  if (!res.ok) throw await errorFrom(res);
  return res;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export async function parseResume(file: File, signal?: AbortSignal): Promise<ParsedResume> {
  const form = new FormData();
  form.append("file", file);
  const res = await request("/api/resume/parse", { method: "POST", body: form, signal });
  return res.json();
}

export async function tailorResume(params: {
  jobDescription: string;
  parsed: ParsedResume;
  sections: Section[];
  intensity: Intensity;
  pageTarget: PageTarget;
  jdKeywords?: string[];
}): Promise<TailorResult> {
  const res = await request(
    "/api/resume/tailor",
    json({
      job_description: params.jobDescription,
      resume_text: params.parsed.text,
      resume: params.parsed.resume,
      sections: params.sections,
      intensity: params.intensity,
      page_target: params.pageTarget,
      jd_keywords: params.jdKeywords,
    }),
  );
  return res.json();
}

/** Streams the cover letter, calling onChunk with each piece of text as it arrives. */
export async function streamCoverLetter(
  params: { jobDescription: string; resume: Resume; tone: CoverLetterTone },
  onChunk: (text: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await request("/api/cover-letter", {
    ...json({ job_description: params.jobDescription, resume: params.resume, tone: params.tone }),
    signal,
  });
  if (!res.body) {
    onChunk(await res.text());
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    onChunk(decoder.decode(value, { stream: true }));
  }
}

export async function exportResume(
  resume: Resume,
  format: "pdf" | "docx",
  pageTarget: PageTarget,
): Promise<{ blob: Blob; filename: string }> {
  const res = await request(`/api/export/${format}`, json({ resume, page_target: pageTarget }));
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `resume.${format}`;
  return { blob: await res.blob(), filename };
}
