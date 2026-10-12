"use client";

import { Check, Copy, Download, PenLine, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ApiError, streamCoverLetter } from "@/lib/api";
import type { CoverLetterTone, Resume } from "@/lib/types";
import { cn, downloadBlob, safeFileName } from "@/lib/utils";
import { Button, ErrorMessage } from "./ui";

const TONES: CoverLetterTone[] = ["professional", "enthusiastic", "concise"];

export function CoverLetter({
  jobDescription,
  resume,
  letter,
  onLetterChange,
}: {
  jobDescription: string;
  resume: Resume;
  letter: string;
  onLetterChange: (text: string) => void;
}) {
  const [tone, setTone] = useState<CoverLetterTone>("professional");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const generate = async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setError(null);
    setStreaming(true);
    let text = "";
    onLetterChange("");
    try {
      await streamCoverLetter(
        { jobDescription, resume, tone },
        (chunk) => {
          text += chunk;
          onLetterChange(text);
        },
        controller.signal,
      );
    } catch (e) {
      if (!controller.signal.aborted) setError(e instanceof ApiError ? e.message : "Couldn't generate the cover letter.");
    } finally {
      if (abortRef.current === controller) setStreaming(false);
    }
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(letter);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setError("Couldn't access the clipboard — select the text and copy it manually.");
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white p-3">
        <span className="text-sm font-medium text-slate-700">Tone</span>
        <div className="flex gap-1 rounded-lg bg-slate-100 p-1">
          {TONES.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTone(t)}
              aria-pressed={tone === t}
              className={cn(
                "rounded-md px-2.5 py-1 text-xs font-medium capitalize transition",
                tone === t ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800",
              )}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="ml-auto flex gap-2">
          {streaming ? (
            <Button onClick={() => abortRef.current?.abort()}>
              <Square className="size-3.5" /> Stop
            </Button>
          ) : (
            <Button variant="primary" onClick={generate}>
              <PenLine className="size-4" /> {letter ? "Regenerate" : "Write cover letter"}
            </Button>
          )}
        </div>
      </div>

      {error && <ErrorMessage>{error}</ErrorMessage>}

      {letter || streaming ? (
        <div className="rounded-xl border border-slate-200 bg-white">
          <div className="flex items-center justify-end gap-1 border-b border-slate-100 px-3 py-2">
            <Button variant="ghost" onClick={copy} disabled={!letter || streaming}>
              {copied ? <Check className="size-4 text-emerald-600" /> : <Copy className="size-4" />}
              {copied ? "Copied" : "Copy"}
            </Button>
            <Button
              variant="ghost"
              disabled={!letter || streaming}
              onClick={() =>
                downloadBlob(new Blob([letter], { type: "text/plain;charset=utf-8" }), `${safeFileName(resume.name)}_Cover_Letter.txt`)
              }
            >
              <Download className="size-4" /> .txt
            </Button>
          </div>
          <div
            className={cn(
              "min-h-48 whitespace-pre-wrap p-5 text-sm leading-relaxed text-slate-700 sm:p-7",
              streaming && "stream-caret",
            )}
            aria-live="polite"
          >
            {letter}
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-slate-200 bg-white/60 px-6 py-12 text-center text-sm text-slate-500">
          Generate a cover letter written from your tailored resume and this job description. It streams in live.
        </div>
      )}
    </div>
  );
}
