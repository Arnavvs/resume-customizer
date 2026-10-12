"use client";

import { Bot, Check, Copy, X } from "lucide-react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { MCP_URL } from "@/lib/api";
import { cn } from "@/lib/utils";

function CopyBlock({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked: the text is still selectable */
    }
  };
  return (
    <div>
      <p className="mb-1 text-xs font-medium text-slate-500">{label}</p>
      <div className="flex items-start gap-2 rounded-lg bg-slate-900 p-2.5">
        <pre className="min-w-0 flex-1 overflow-x-auto whitespace-pre-wrap break-all font-mono text-xs leading-relaxed text-slate-100">
          {value}
        </pre>
        <button
          type="button"
          onClick={copy}
          className="shrink-0 rounded-md p-1 text-slate-400 hover:bg-slate-700 hover:text-white"
          aria-label={`Copy ${label}`}
        >
          {copied ? <Check className="size-3.5 text-emerald-400" /> : <Copy className="size-3.5" />}
        </button>
      </div>
    </div>
  );
}

const CLIENTS = (url: string) => [
  { id: "claude-code", label: "Claude Code", value: `claude mcp add --transport http resume-customizer ${url}` },
  { id: "codex", label: "Codex CLI", value: `codex mcp add resume-customizer --url ${url}` },
  {
    id: "json",
    label: "Cursor / VS Code / other (mcp.json)",
    value: JSON.stringify({ mcpServers: { "resume-customizer": { url } } }, null, 2),
  },
];

export function AgentConnect({ webMcpActive }: { webMcpActive: boolean }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50 hover:text-slate-900"
      >
        <Bot className="size-3.5" aria-hidden />
        <span className="hidden sm:inline">Connect AI agent</span>
        <span className="sm:hidden">MCP</span>
      </button>

      {/* Portal: the sticky header's backdrop-filter would otherwise trap this fixed overlay. */}
      {open &&
        createPortal(
          <div
            // `m-auto` centres the dialog when it fits and lets the overlay scroll when it doesn't.
            className="fixed inset-0 z-50 flex overflow-y-auto bg-slate-900/40 p-4 backdrop-blur-sm"
            onClick={() => setOpen(false)}
            role="presentation"
          >
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="agent-title"
              className="m-auto w-full max-w-lg rounded-2xl bg-white p-5 shadow-xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="mb-3 flex items-start justify-between gap-4">
                <div>
                  <h2 id="agent-title" className="flex items-center gap-2 font-semibold text-slate-900">
                    <Bot className="size-4 text-indigo-600" /> Use Resume Customizer from your AI agent
                  </h2>
                  <p className="mt-1 text-sm text-slate-500">
                    The backend is also a remote <strong>MCP server</strong>. Add it to Claude, Codex or any MCP client
                    — no install or API key — and ask:{" "}
                    <em>&ldquo;Tailor my resume (attached) to this job and give me the PDF&rdquo;</em>.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                  aria-label="Close"
                >
                  <X className="size-4" />
                </button>
              </div>

              <div className="space-y-3">
                <CopyBlock label="MCP server URL (Streamable HTTP)" value={MCP_URL} />
                {CLIENTS(MCP_URL).map((c) => (
                  <CopyBlock key={c.id} label={c.label} value={c.value} />
                ))}
                <p className="text-xs text-slate-500">
                  <strong>claude.ai / Claude Desktop:</strong> Settings → Connectors → Add custom connector → paste the
                  URL.
                </p>
              </div>

              <div className="mt-4 rounded-xl bg-slate-50 p-3 text-xs text-slate-600">
                <p className="font-medium text-slate-800">Tools</p>
                <ul className="mt-1 list-disc space-y-0.5 pl-4">
                  <li>
                    <code>tailor_resume</code> — JD + resume text or file → tailored resume, scores, gaps, PDF/DOCX
                    links
                  </li>
                  <li>
                    <code>write_cover_letter</code> — grounded cover letter
                  </li>
                  <li>
                    <code>export_resume</code> — PDF/DOCX link for an edited resume
                  </li>
                  <li>
                    <code>run_sample_demo</code> — try it end to end with sample data
                  </li>
                </ul>
                <p className="mt-2 flex items-center gap-1.5">
                  <span className={cn("size-1.5 rounded-full", webMcpActive ? "bg-emerald-500" : "bg-slate-300")} />
                  WebMCP (in-browser agents):{" "}
                  {webMcpActive ? "this page is exposing its tools now." : "not supported by this browser."}
                </p>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
