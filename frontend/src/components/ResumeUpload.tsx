"use client";

import { CheckCircle2, FileText, Loader2, Upload, X } from "lucide-react";
import { useRef, useState } from "react";
import type { ParsedResume } from "@/lib/types";
import { cn, formatBytes } from "@/lib/utils";
import { ErrorMessage, StepLabel } from "./ui";

export const MAX_UPLOAD_MB = 5;
const ACCEPTED = [".pdf", ".docx"];

export function validateFile(file: File): string | null {
  const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
  if (!ACCEPTED.includes(ext)) {
    return ext === ".doc"
      ? "Old .doc files aren't supported — please save it as .docx or PDF."
      : "Unsupported file type. Please upload a PDF or DOCX file.";
  }
  if (file.size === 0) return "This file is empty.";
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    return `File is too large (${formatBytes(file.size)}). The maximum is ${MAX_UPLOAD_MB} MB.`;
  }
  return null;
}

export function ResumeUpload({
  file,
  parsed,
  parsing,
  error,
  onSelect,
  onClear,
}: {
  file: { name: string; size: number } | null;
  parsed: ParsedResume | null;
  parsing: boolean;
  error: string | null;
  onSelect: (file: File) => void;
  onClear: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const pick = (files: FileList | null) => {
    if (files?.[0]) onSelect(files[0]);
    if (inputRef.current) inputRef.current.value = ""; // allow re-selecting the same file
  };

  return (
    <div className="space-y-2">
      <StepLabel n={2}>Your resume</StepLabel>

      {file ? (
        <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50/60 p-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-white ring-1 ring-slate-200">
            <FileText className="size-5 text-indigo-600" aria-hidden />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-slate-800" title={file.name}>
              {file.name}
            </p>
            <p className="flex flex-wrap items-center gap-x-1.5 whitespace-nowrap text-xs text-slate-500">
              {formatBytes(file.size)}
              {parsing && (
                <>
                  <span aria-hidden>·</span>
                  <Loader2 className="size-3 animate-spin" aria-hidden /> Reading resume…
                </>
              )}
              {parsed && !parsing && (
                <>
                  <span aria-hidden>·</span>
                  <CheckCircle2 className="size-3 text-emerald-600" aria-hidden />
                  <span className="text-emerald-700">
                    Parsed {parsed.resume.experience.length} roles, {parsed.resume.skills.reduce((n, g) => n + g.skills.length, 0)} skills
                  </span>
                </>
              )}
            </p>
          </div>
          <button
            type="button"
            onClick={onClear}
            className="rounded-md p-1.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700"
            aria-label="Remove file"
          >
            <X className="size-4" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            pick(e.dataTransfer.files);
          }}
          className={cn(
            "flex w-full flex-col items-center gap-2 rounded-xl border-2 border-dashed px-4 py-7 text-center transition",
            dragging ? "border-indigo-400 bg-indigo-50" : "border-slate-200 bg-slate-50/60 hover:border-indigo-300 hover:bg-indigo-50/40",
          )}
        >
          <Upload className="size-6 text-indigo-500" aria-hidden />
          <span className="text-sm font-medium text-slate-700">
            Drop your resume here or <span className="text-indigo-600 underline underline-offset-2">browse</span>
          </span>
          <span className="text-xs text-slate-400">PDF or DOCX · up to {MAX_UPLOAD_MB} MB</span>
        </button>
      )}
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        className="hidden"
        onChange={(e) => pick(e.target.files)}
        data-testid="resume-input"
      />
      {error && <ErrorMessage>{error}</ErrorMessage>}
    </div>
  );
}
