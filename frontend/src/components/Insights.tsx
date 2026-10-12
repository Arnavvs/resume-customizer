import { ArrowRight, Check, Lightbulb, Sparkles, X } from "lucide-react";
import type { ReactNode } from "react";
import type { TailorResult } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Chip } from "./ui";

function scoreColor(score: number) {
  if (score >= 75) return "text-emerald-600";
  if (score >= 50) return "text-amber-600";
  return "text-red-600";
}

function Ring({ value, size = 76 }: { value: number; size?: number }) {
  const r = (size - 10) / 2;
  const c = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className={scoreColor(value)} aria-hidden>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e2e8f0" strokeWidth="7" />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="currentColor"
        strokeWidth="7"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={c * (1 - value / 100)}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: "stroke-dashoffset .8s ease" }}
      />
      <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle" className="fill-slate-900 text-lg font-bold">
        {value}
      </text>
    </svg>
  );
}

export function ScoreCard({ title, hint, before, after }: { title: string; hint: string; before: number; after: number }) {
  const delta = after - before;
  return (
    <div className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-4">
      <Ring value={after} />
      <div className="min-w-0">
        <p className="text-sm font-semibold text-slate-900">{title}</p>
        <p className="mt-0.5 flex items-center gap-1.5 text-sm text-slate-500">
          <span className="tabular-nums">{before}%</span>
          <ArrowRight className="size-3.5" aria-hidden />
          <span className={cn("font-semibold tabular-nums", scoreColor(after))}>{after}%</span>
          {delta !== 0 && (
            <span className={cn("text-xs font-medium", delta > 0 ? "text-emerald-600" : "text-red-600")}>
              ({delta > 0 ? "+" : ""}
              {delta})
            </span>
          )}
        </p>
        <p className="mt-1 text-xs text-slate-400">{hint}</p>
      </div>
    </div>
  );
}

function Panel({ title, icon, children }: { title: string; icon?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4">
      <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900">
        {icon}
        {title}
      </h3>
      {children}
    </section>
  );
}

const IMPORTANCE_TONE = { high: "red", medium: "amber", low: "slate" } as const;

export function Insights({ result }: { result: TailorResult }) {
  const { scores } = result;
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <ScoreCard
          title="JD keyword match"
          hint="Share of the JD's key terms found in the resume"
          before={scores.match_before.score}
          after={scores.match_after.score}
        />
        <ScoreCard
          title="ATS readiness"
          hint="Keywords, structure, action verbs, metrics"
          before={scores.ats_before.score}
          after={scores.ats_after.score}
        />
      </div>

      <Panel title="What changed" icon={<Sparkles className="size-4 text-indigo-500" />}>
        <ul className="space-y-1.5 text-sm text-slate-700">
          {result.change_log.map((c, i) => (
            <li key={i} className="flex gap-2">
              <span className="mt-2 size-1.5 shrink-0 rounded-full bg-indigo-400" aria-hidden />
              {c}
            </li>
          ))}
        </ul>
      </Panel>

      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title={`Keywords you match (${scores.match_after.matched.length})`} icon={<Check className="size-4 text-emerald-600" />}>
          <div className="flex flex-wrap gap-1.5">
            {scores.match_after.matched.length ? (
              scores.match_after.matched.map((k) => (
                <Chip key={k} tone="green">
                  {k}
                </Chip>
              ))
            ) : (
              <p className="text-sm text-slate-500">No direct keyword matches yet.</p>
            )}
          </div>
        </Panel>

        <Panel title={`Not in your resume (${scores.match_after.missing.length})`} icon={<X className="size-4 text-red-500" />}>
          <div className="flex flex-wrap gap-1.5">
            {scores.match_after.missing.length ? (
              scores.match_after.missing.map((k) => (
                <Chip key={k} tone="red">
                  {k}
                </Chip>
              ))
            ) : (
              <p className="text-sm text-slate-500">Every key JD term appears in your resume.</p>
            )}
          </div>
        </Panel>
      </div>

      {result.missing_keywords.length > 0 && (
        <Panel title="Suggestions to close the gaps" icon={<Lightbulb className="size-4 text-amber-500" />}>
          <p className="-mt-1 mb-3 text-xs text-slate-500">
            These weren&apos;t added automatically — only add them if they&apos;re true for you.
          </p>
          <ul className="divide-y divide-slate-100">
            {result.missing_keywords.map((k) => (
              <li key={k.keyword} className="flex flex-col gap-1 py-2.5 first:pt-0 last:pb-0 sm:flex-row sm:gap-3">
                <div className="flex shrink-0 items-center gap-2 sm:w-44">
                  <span className="text-sm font-medium text-slate-900">{k.keyword}</span>
                  <Chip tone={IMPORTANCE_TONE[k.importance]}>{k.importance}</Chip>
                </div>
                <p className="text-sm text-slate-600">{k.suggestion}</p>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      <Panel title="ATS checklist">
        <ul className="space-y-2">
          {scores.ats_after.checks.map((c) => (
            <li key={c.label} className="flex items-start gap-3 text-sm">
              <span
                className={cn(
                  "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full",
                  c.passed ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700",
                )}
              >
                {c.passed ? <Check className="size-3" /> : <span className="text-xs font-bold">!</span>}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex justify-between gap-2">
                  <span className="font-medium text-slate-800">{c.label}</span>
                  <span className="tabular-nums text-xs text-slate-400">
                    {c.points}/{c.max_points}
                  </span>
                </div>
                <p className="text-xs text-slate-500">{c.detail}</p>
              </div>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
