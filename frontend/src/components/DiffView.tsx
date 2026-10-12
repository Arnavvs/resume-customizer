import { diffWords } from "diff";
import type { ReactNode } from "react";
import type { Resume } from "@/lib/types";

/** Above this share of changed text an inline diff is unreadable, so show before/after instead. */
const REWRITE_THRESHOLD = 0.55;

function InlineDiff({ before, after }: { before: string; after: string }) {
  if (before === after) return <span className="text-slate-500">{after || <em>— empty —</em>}</span>;
  const parts = diffWords(before, after);
  const changed = parts.filter((p) => p.added || p.removed).reduce((n, p) => n + p.value.length, 0);
  const rewritten = !before || changed / (before.length + after.length) > REWRITE_THRESHOLD;

  if (rewritten) {
    return (
      <span className="grid gap-2 md:grid-cols-2">
        <span className="block rounded-lg bg-red-50/60 p-3 ring-1 ring-red-100">
          <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-red-700">Before</span>
          <span className="text-slate-500">{before || <em>— empty —</em>}</span>
        </span>
        <span className="block rounded-lg bg-emerald-50/60 p-3 ring-1 ring-emerald-100">
          <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-emerald-700">After</span>
          <span className="text-slate-800">{after}</span>
        </span>
      </span>
    );
  }

  return (
    <>
      {parts.map((part, i) =>
        part.added ? (
          <ins key={i} className="diff-add">
            {part.value}
          </ins>
        ) : part.removed ? (
          <del key={i} className="diff-del">
            {part.value}
          </del>
        ) : (
          <span key={i}>{part.value}</span>
        ),
      )}
    </>
  );
}

function Block({ title, changed, children }: { title: string; changed: boolean; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
        <span className={changed ? "text-xs font-medium text-indigo-600" : "text-xs text-slate-400"}>
          {changed ? "Modified" : "Unchanged"}
        </span>
      </div>
      <div className="text-sm leading-relaxed text-slate-700">{children}</div>
    </section>
  );
}

const skillsText = (r: Resume) => r.skills.map((g) => `${g.category}: ${g.skills.join(", ")}`).join("\n");
const bulletsText = (bullets: string[]) => bullets.map((b) => `• ${b}`).join("\n");

export function DiffView({ original, tailored }: { original: Resume; tailored: Resume }) {
  const origProjects = new Map(original.projects.map((p) => [p.name, p]));

  return (
    <div className="space-y-3">
      <p className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
        <span>
          <ins className="diff-add px-1">added</ins> / <del className="diff-del px-1">removed</del> words, compared with your
          original resume.
        </span>
      </p>

      <Block title="Summary" changed={original.summary !== tailored.summary}>
        <p>
          <InlineDiff before={original.summary} after={tailored.summary} />
        </p>
      </Block>

      <Block title="Skills" changed={skillsText(original) !== skillsText(tailored)}>
        <p className="whitespace-pre-line">
          <InlineDiff before={skillsText(original)} after={skillsText(tailored)} />
        </p>
      </Block>

      {tailored.experience.map((job, i) => {
        const before = bulletsText(original.experience[i]?.bullets ?? []);
        const after = bulletsText(job.bullets);
        return (
          <Block key={`exp-${i}`} title={`${job.title} — ${job.company}`} changed={before !== after}>
            <p className="whitespace-pre-line">
              <InlineDiff before={before} after={after} />
            </p>
          </Block>
        );
      })}

      {tailored.projects.map((proj, i) => {
        // Projects may be reordered by relevance, so match them by name.
        const before = bulletsText(origProjects.get(proj.name)?.bullets ?? original.projects[i]?.bullets ?? []);
        const after = bulletsText(proj.bullets);
        return (
          <Block key={`proj-${i}`} title={`Project: ${proj.name}`} changed={before !== after}>
            <p className="whitespace-pre-line">
              <InlineDiff before={before} after={after} />
            </p>
          </Block>
        );
      })}
    </div>
  );
}
