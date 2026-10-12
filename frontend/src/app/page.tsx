"use client";

import { Briefcase, FileSearch, GitCompare, Loader2, PenLine, Plus, Sparkles, Trash2, Wand2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { CompareView } from "@/components/CompareView";
import { CoverLetter } from "@/components/CoverLetter";
import { DiffView } from "@/components/DiffView";
import { DownloadMenu } from "@/components/DownloadMenu";
import { Insights } from "@/components/Insights";
import { JobDescriptionInput, jdError } from "@/components/JobDescriptionInput";
import { ResumeUpload, validateFile } from "@/components/ResumeUpload";
import { ResumeView } from "@/components/ResumeView";
import { ALL_SECTIONS, TailorOptions } from "@/components/TailorOptions";
import { Button, Card, Chip, ErrorMessage } from "@/components/ui";
import { ApiError, parseResume, tailorResume } from "@/lib/api";
import type { Intensity, ParsedResume, ResumeVersion, Section } from "@/lib/types";
import { cn, storage } from "@/lib/utils";

type Tab = "resume" | "changes" | "insights" | "cover" | "compare";

const TABS: { id: Tab; label: string; icon: typeof Sparkles }[] = [
  { id: "resume", label: "Resume", icon: Briefcase },
  { id: "changes", label: "Changes", icon: FileSearch },
  { id: "insights", label: "Scores & gaps", icon: Sparkles },
  { id: "cover", label: "Cover letter", icon: PenLine },
  { id: "compare", label: "Compare", icon: GitCompare },
];

const PROGRESS_STEPS = [
  "Reading the job description…",
  "Finding the keywords that matter…",
  "Matching them to your experience…",
  "Rewriting your summary and bullets…",
  "Scoring the result…",
];

const STORAGE_KEY = "resume-customizer:v1";

interface Persisted {
  jd: string;
  parsed: ParsedResume | null;
  versions: ResumeVersion[];
  activeId: string | null;
  coverLetters: Record<string, string>;
}

const INTENSITY_LABEL: Record<Intensity, string> = { conservative: "Light", balanced: "Balanced", bold: "Bold" };

function versionLabel(n: number, intensity: Intensity, sections: Section[]) {
  const scope =
    sections.length === ALL_SECTIONS.length
      ? "all sections"
      : sections.map((s) => ALL_SECTIONS.find((a) => a.id === s)?.label).join(", ");
  return `v${n} · ${INTENSITY_LABEL[intensity]} · ${scope}`;
}

export default function Home() {
  const [jd, setJd] = useState("");
  const [file, setFile] = useState<{ name: string; size: number } | null>(null);
  const [parsed, setParsed] = useState<ParsedResume | null>(null);
  const [parsing, setParsing] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [sections, setSections] = useState<Section[]>(ALL_SECTIONS.map((s) => s.id));
  const [intensity, setIntensity] = useState<Intensity>("balanced");

  const [versions, setVersions] = useState<ResumeVersion[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [coverLetters, setCoverLetters] = useState<Record<string, string>>({});
  const [tab, setTab] = useState<Tab>("resume");

  const [tailoring, setTailoring] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  const parseAbort = useRef<AbortController | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  // Restore the last session so a refresh doesn't lose work.
  useEffect(() => {
    const saved = storage.get<Persisted>(STORAGE_KEY);
    if (saved) {
      setJd(saved.jd ?? "");
      if (saved.parsed) {
        setParsed(saved.parsed);
        setFile({ name: saved.parsed.filename, size: saved.parsed.size_bytes });
      }
      setVersions(saved.versions ?? []);
      setActiveId(saved.activeId ?? null);
      setCoverLetters(saved.coverLetters ?? {});
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (hydrated) storage.set(STORAGE_KEY, { jd, parsed, versions, activeId, coverLetters } satisfies Persisted);
  }, [hydrated, jd, parsed, versions, activeId, coverLetters]);

  useEffect(() => {
    if (!tailoring) return;
    setProgress(0);
    const id = setInterval(() => setProgress((p) => Math.min(p + 1, PROGRESS_STEPS.length - 1)), 3500);
    return () => clearInterval(id);
  }, [tailoring]);

  const handleFile = useCallback(async (f: File) => {
    parseAbort.current?.abort();
    setUploadError(null);
    setParsed(null);
    const invalid = validateFile(f);
    if (invalid) {
      setFile(null);
      setUploadError(invalid);
      return;
    }
    setFile({ name: f.name, size: f.size });
    const controller = new AbortController();
    parseAbort.current = controller;
    setParsing(true);
    try {
      setParsed(await parseResume(f, controller.signal));
    } catch (e) {
      if (controller.signal.aborted) return;
      setUploadError(e instanceof ApiError ? e.message : "Couldn't read this file. Please try another one.");
    } finally {
      if (parseAbort.current === controller) setParsing(false);
    }
  }, []);

  const loadSample = async () => {
    try {
      const [jdText, resumeBlob] = await Promise.all([
        fetch("/samples/job_description.txt").then((r) => r.text()),
        fetch("/samples/sample_resume.docx").then((r) => r.blob()),
      ]);
      setJd(jdText);
      await handleFile(new File([resumeBlob], "sample_resume.docx", { type: resumeBlob.type }));
    } catch {
      setUploadError("Couldn't load the sample files.");
    }
  };

  const clearFile = () => {
    parseAbort.current?.abort();
    setParsing(false);
    setFile(null);
    setParsed(null);
    setUploadError(null);
  };

  const jdInvalid = jdError(jd);
  const canSubmit = !jdInvalid && !!parsed && sections.length > 0 && !tailoring && !parsing;

  const handleTailor = async () => {
    setSubmitted(true);
    setError(null);
    if (jdInvalid) return;
    if (!parsed) {
      setUploadError(parsing ? "Still reading your resume — one moment." : "Upload your resume (PDF or DOCX) to continue.");
      return;
    }
    if (!sections.length) return;

    setTailoring(true);
    try {
      const jobDescription = jd.trim();
      // Score new versions of the same JD against the same keyword list so they're comparable.
      const sameJd = versions.find((v) => v.jobDescription === jobDescription);
      const result = await tailorResume({
        jobDescription,
        parsed,
        sections,
        intensity,
        jdKeywords: sameJd?.jd_keywords,
      });
      const version: ResumeVersion = {
        ...result,
        id: crypto.randomUUID(),
        label: versionLabel(versions.length + 1, intensity, result.sections),
        createdAt: Date.now(),
        jobDescription,
      };
      setVersions((v) => [...v, version]);
      setActiveId(version.id);
      setTab("resume");
      requestAnimationFrame(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong while tailoring. Please try again.");
    } finally {
      setTailoring(false);
    }
  };

  const resetAll = () => {
    setVersions([]);
    setActiveId(null);
    setCoverLetters({});
    setTab("resume");
  };

  const active = versions.find((v) => v.id === activeId) ?? versions[versions.length - 1] ?? null;

  return (
    <div className="min-h-screen">
      <header className="no-print sticky top-0 z-20 border-b border-slate-200/80 bg-white/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-2">
            <div className="flex size-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-600 to-violet-600 text-white shadow-sm">
              <Wand2 className="size-4" aria-hidden />
            </div>
            <span className="font-semibold tracking-tight text-slate-900">Resume Customizer</span>
          </div>
          <span className="hidden text-xs text-slate-500 sm:block">Tailor your resume to any job · powered by Gemini</span>
        </div>
      </header>

      <main className="mx-auto grid max-w-7xl gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[400px_minmax(0,1fr)] lg:py-8">
        {/* ------------------------------------------------ Inputs */}
        <aside className="no-print lg:sticky lg:top-20 lg:self-start">
          <Card className="space-y-6 p-5">
            {!jd && !file && (
              <button
                type="button"
                onClick={loadSample}
                className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-indigo-50 px-3 py-2 text-xs font-medium text-indigo-700 hover:bg-indigo-100"
              >
                <Sparkles className="size-3.5" /> No resume handy? Try it with a sample JD + resume
              </button>
            )}
            <JobDescriptionInput value={jd} onChange={setJd} showError={submitted} />
            <ResumeUpload
              file={file}
              parsed={parsed}
              parsing={parsing}
              error={uploadError}
              onSelect={handleFile}
              onClear={clearFile}
            />
            <TailorOptions
              sections={sections}
              onSectionsChange={setSections}
              intensity={intensity}
              onIntensityChange={setIntensity}
            />
            <div className="space-y-2">
              <Button
                variant="primary"
                className="w-full py-2.5 text-[15px]"
                onClick={handleTailor}
                loading={tailoring}
                disabled={tailoring || (submitted && !canSubmit)}
              >
                {!tailoring && (versions.length ? <Plus className="size-4" /> : <Sparkles className="size-4" />)}
                {tailoring ? "Tailoring…" : versions.length ? "Generate new version" : "Tailor my resume"}
              </Button>
              {error && <ErrorMessage>{error}</ErrorMessage>}
            </div>
          </Card>
        </aside>

        {/* ------------------------------------------------ Results */}
        <section ref={resultsRef} className="min-w-0 scroll-mt-20" aria-live="polite">
          {tailoring && !active ? (
            <LoadingState step={progress} />
          ) : active ? (
            <div className="space-y-4">
              <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
                <div className="min-w-0">
                  <p className="text-xs font-medium uppercase tracking-wider text-indigo-600">Tailored for</p>
                  <h1 className="truncate text-xl font-semibold tracking-tight text-slate-900">{active.target_role}</h1>
                </div>
                <div className="no-print">
                  <DownloadMenu resume={active.resume} onError={setError} />
                </div>
              </div>

              <div className="no-print flex flex-wrap items-center gap-2">
                {versions.map((v) => (
                  <button
                    key={v.id}
                    onClick={() => setActiveId(v.id)}
                    className={cn(
                      "rounded-full px-3 py-1 text-xs font-medium ring-1 transition",
                      v.id === active.id
                        ? "bg-slate-900 text-white ring-slate-900"
                        : "bg-white text-slate-600 ring-slate-200 hover:ring-slate-300",
                    )}
                  >
                    {v.label} · {v.scores.match_after.score}%
                  </button>
                ))}
                {tailoring && (
                  <span className="flex items-center gap-1.5 text-xs text-slate-500">
                    <Loader2 className="size-3 animate-spin" /> {PROGRESS_STEPS[progress]}
                  </span>
                )}
                <button
                  onClick={resetAll}
                  className="ml-auto flex items-center gap-1 rounded-md px-2 py-1 text-xs text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                >
                  <Trash2 className="size-3" /> Clear versions
                </button>
              </div>

              <nav className="no-print -mx-1 flex gap-1 overflow-x-auto border-b border-slate-200 px-1 [scrollbar-width:none]" role="tablist">
                {TABS.map(({ id, label, icon: Icon }) => (
                  <button
                    key={id}
                    role="tab"
                    aria-selected={tab === id}
                    onClick={() => setTab(id)}
                    className={cn(
                      "-mb-px flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2.5 text-sm font-medium transition",
                      tab === id ? "border-indigo-600 text-indigo-700" : "border-transparent text-slate-500 hover:text-slate-800",
                    )}
                  >
                    <Icon className="hidden size-4 xl:block" aria-hidden />
                    {label}
                    {id === "compare" && versions.length > 1 && <Chip tone="indigo">{versions.length}</Chip>}
                  </button>
                ))}
              </nav>

              <div role="tabpanel">
                {tab === "resume" && (
                  <div className="space-y-2">
                    <p className="no-print text-xs text-slate-500">
                      <mark className="rounded bg-amber-100 px-1">Highlighted</mark> terms match the job description.
                    </p>
                    <ResumeView resume={active.resume} keywords={active.scores.match_after.matched} />
                  </div>
                )}
                {tab === "changes" && parsed && <DiffView original={parsed.resume} tailored={active.resume} />}
                {tab === "changes" && !parsed && (
                  <ErrorMessage>Re-upload your original resume to see the changes.</ErrorMessage>
                )}
                {tab === "insights" && <Insights result={active} />}
                {tab === "cover" && (
                  <CoverLetter
                    key={active.id}
                    jobDescription={active.jobDescription ?? jd}
                    resume={active.resume}
                    letter={coverLetters[active.id] ?? ""}
                    onLetterChange={(text) => setCoverLetters((c) => ({ ...c, [active.id]: text }))}
                  />
                )}
                {tab === "compare" && <CompareView versions={versions} />}
              </div>
            </div>
          ) : (
            <EmptyState />
          )}
        </section>
      </main>
    </div>
  );
}

function LoadingState({ step }: { step: number }) {
  return (
    <Card className="p-8">
      <div className="mx-auto max-w-sm space-y-4">
        <div className="flex items-center gap-3">
          <Loader2 className="size-5 animate-spin text-indigo-600" />
          <p className="font-medium text-slate-800">Tailoring your resume</p>
        </div>
        <ol className="space-y-2.5">
          {PROGRESS_STEPS.map((s, i) => (
            <li
              key={s}
              className={cn(
                "flex items-center gap-2.5 text-sm transition-colors",
                i < step ? "text-slate-400" : i === step ? "font-medium text-slate-900" : "text-slate-300",
              )}
            >
              <span
                className={cn("size-2 rounded-full", i < step ? "bg-emerald-500" : i === step ? "animate-pulse bg-indigo-500" : "bg-slate-200")}
              />
              {s}
            </li>
          ))}
        </ol>
        <p className="text-xs text-slate-400">This usually takes 15–40 seconds.</p>
      </div>
    </Card>
  );
}

function EmptyState() {
  const steps = [
    { title: "Paste the job description", body: "We pull out the skills, tools and terms the recruiter's ATS will look for." },
    { title: "Upload your resume", body: "PDF or DOCX. We parse it into sections — nothing is stored on our servers." },
    { title: "Get a tailored version", body: "Rewritten summary, reordered bullets, JD keywords — never invented experience." },
  ];
  return (
    <div className="flex h-full min-h-[420px] flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white/50 px-6 py-12 text-center">
      <div className="flex size-12 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600">
        <Sparkles className="size-6" />
      </div>
      <h1 className="mt-4 text-2xl font-semibold tracking-tight text-slate-900">Land more interviews with a resume built for the job</h1>
      <p className="mt-2 max-w-md text-sm text-slate-500">
        Your tailored resume, a match score, a line-by-line diff and a cover letter will appear here.
      </p>
      <ol className="mt-8 grid w-full max-w-2xl gap-3 text-left sm:grid-cols-3">
        {steps.map((s, i) => (
          <li key={s.title} className="rounded-xl border border-slate-200 bg-white p-4">
            <span className="text-xs font-semibold text-indigo-600">Step {i + 1}</span>
            <p className="mt-1 text-sm font-medium text-slate-900">{s.title}</p>
            <p className="mt-1 text-xs leading-relaxed text-slate-500">{s.body}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}
