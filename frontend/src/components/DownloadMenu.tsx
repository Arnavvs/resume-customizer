"use client";

import { Download, FileText, FileType2, FileCode2 } from "lucide-react";
import { useState } from "react";
import { ApiError, exportResume } from "@/lib/api";
import type { Resume } from "@/lib/types";
import { downloadBlob, resumeToText, safeFileName } from "@/lib/utils";
import { Button } from "./ui";

type Format = "pdf" | "docx" | "txt";

export function DownloadMenu({ resume, onError }: { resume: Resume; onError: (msg: string) => void }) {
  const [busy, setBusy] = useState<Format | null>(null);

  const download = async (format: Format) => {
    if (format === "txt") {
      const blob = new Blob([resumeToText(resume)], { type: "text/plain;charset=utf-8" });
      downloadBlob(blob, `${safeFileName(resume.name)}_Resume.txt`);
      return;
    }
    setBusy(format);
    try {
      const { blob, filename } = await exportResume(resume, format);
      downloadBlob(blob, filename);
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "Download failed. Please try again.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="hidden items-center gap-1.5 text-sm text-slate-500 sm:flex">
        <Download className="size-4" aria-hidden /> Download
      </span>
      <Button variant="primary" loading={busy === "pdf"} onClick={() => download("pdf")}>
        {busy !== "pdf" && <FileText className="size-4" aria-hidden />} PDF
      </Button>
      <Button loading={busy === "docx"} onClick={() => download("docx")}>
        {busy !== "docx" && <FileType2 className="size-4" aria-hidden />} DOCX
      </Button>
      <Button onClick={() => download("txt")}>
        <FileCode2 className="size-4" aria-hidden /> TXT
      </Button>
    </div>
  );
}
