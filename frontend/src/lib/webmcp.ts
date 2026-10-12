/**
 * WebMCP: lets an AI agent running in the browser (e.g. Chrome's built-in agent) use this page
 * through tools, instead of clicking around the UI. Experimental web platform API, so everything
 * here is feature-detected and a no-op where unsupported.
 * Spec/docs: https://developer.chrome.com/docs/ai/webmcp/imperative-api
 */

import type { ResumeVersion } from "./types";
import { resumeToText } from "./utils";

export interface WebMcpTool {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  annotations?: { readOnlyHint?: boolean };
  execute: (args: Record<string, unknown>) => Promise<string>;
}

interface ModelContext {
  registerTool(tool: WebMcpTool, options?: { signal?: AbortSignal }): Promise<void> | void;
}

function modelContext(): ModelContext | null {
  // Current Chrome docs use document.modelContext; earlier previews used navigator.modelContext.
  const candidate =
    (document as unknown as { modelContext?: ModelContext }).modelContext ??
    (navigator as unknown as { modelContext?: ModelContext }).modelContext;
  return candidate && typeof candidate.registerTool === "function" ? candidate : null;
}

/** Registers the tools; returns false when the browser has no WebMCP support. Abort to unregister. */
export async function registerWebMcpTools(tools: WebMcpTool[], signal: AbortSignal): Promise<boolean> {
  const mc = modelContext();
  if (!mc) return false;
  for (const tool of tools) {
    try {
      await mc.registerTool(tool, { signal });
    } catch (e) {
      console.warn(`WebMCP: could not register ${tool.name}`, e);
    }
  }
  return true;
}

export function describeVersion(v: ResumeVersion): string {
  const s = v.scores;
  const gaps = v.missing_keywords.map((k) => `- ${k.keyword} (${k.importance}): ${k.suggestion}`).join("\n");
  return [
    `Tailored for: ${v.target_role} (${v.label})`,
    `PDF length: ${v.page_count} page(s)`,
    `JD keyword match: ${s.match_before.score}% -> ${s.match_after.score}%`,
    `ATS readiness: ${s.ats_before.score} -> ${s.ats_after.score}`,
    "",
    "What changed:",
    ...v.change_log.map((c) => `- ${c}`),
    "",
    gaps ? `Gaps to address honestly:\n${gaps}\n` : "",
    "Tailored resume:",
    resumeToText(v.resume),
    "",
    "The user can download it as PDF/DOCX with the buttons on the page.",
  ].join("\n");
}
