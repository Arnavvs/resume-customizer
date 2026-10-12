import type { ReactNode } from "react";
import type { Resume } from "@/lib/types";
import { cn } from "@/lib/utils";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-5 first:mt-0">
      <h3 className="mb-2 border-b border-slate-300 pb-1 text-xs font-bold uppercase tracking-[0.14em] text-indigo-900">
        {title}
      </h3>
      {children}
    </section>
  );
}

function Entry({ left, right }: { left: string; right?: string }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4">
      <p className="font-semibold text-slate-900">{left}</p>
      {right && <p className="text-xs italic text-slate-500">{right}</p>}
    </div>
  );
}

function Bullets({ items, highlight }: { items: string[]; highlight: (t: string) => ReactNode }) {
  return (
    <ul className="mt-1 list-disc space-y-1 pl-5 marker:text-slate-400">
      {items.map((b, i) => (
        <li key={i}>{highlight(b)}</li>
      ))}
    </ul>
  );
}

/** Wraps occurrences of the given keywords in <mark>. */
function makeHighlighter(keywords: string[]) {
  const terms = keywords.filter((k) => k.trim().length > 1).sort((a, b) => b.length - a.length);
  if (!terms.length) return (t: string) => t;
  const escaped = terms.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const re = new RegExp(`(?<![A-Za-z0-9])(${escaped.join("|")})(?![A-Za-z0-9+#])`, "gi");
  return (text: string): ReactNode => {
    const parts = text.split(re);
    return parts.map((part, i) =>
      i % 2 === 1 ? (
        <mark key={i} className="rounded bg-amber-100 px-0.5 text-inherit">
          {part}
        </mark>
      ) : (
        part
      ),
    );
  };
}

export function ResumeView({
  resume,
  keywords = [],
  compact = false,
}: {
  resume: Resume;
  keywords?: string[];
  compact?: boolean;
}) {
  const hl = makeHighlighter(keywords);
  return (
    <article
      className={cn(
        "mx-auto max-w-[800px] rounded-lg bg-white text-slate-700 shadow-[0_1px_3px_rgba(15,23,42,.08),0_8px_24px_rgba(15,23,42,.06)] ring-1 ring-slate-200",
        compact ? "p-5 text-[12.5px] leading-relaxed" : "p-6 text-sm leading-relaxed sm:p-10",
      )}
    >
      <header className="mb-5 text-center">
        <h2 className={cn("font-bold tracking-tight text-slate-900", compact ? "text-xl" : "text-2xl sm:text-3xl")}>
          {resume.name}
        </h2>
        {resume.headline && <p className="mt-0.5 font-medium text-slate-600">{resume.headline}</p>}
        {resume.contact.length > 0 && (
          <p className="mt-1 break-words text-xs text-slate-500">{resume.contact.join("  ·  ")}</p>
        )}
      </header>

      {resume.summary && (
        <Section title="Summary">
          <p>{hl(resume.summary)}</p>
        </Section>
      )}

      {resume.skills.length > 0 && (
        <Section title="Skills">
          <div className="space-y-1">
            {resume.skills.map((g, i) => (
              <p key={i}>
                {g.category && <span className="font-semibold text-slate-900">{g.category}: </span>}
                {hl(g.skills.join(", "))}
              </p>
            ))}
          </div>
        </Section>
      )}

      {resume.experience.length > 0 && (
        <Section title="Experience">
          <div className="space-y-3">
            {resume.experience.map((job, i) => (
              <div key={i}>
                <Entry
                  left={[job.title, job.company].filter(Boolean).join(" — ")}
                  right={[job.location, job.dates].filter(Boolean).join(" | ")}
                />
                <Bullets items={job.bullets} highlight={hl} />
              </div>
            ))}
          </div>
        </Section>
      )}

      {resume.projects.length > 0 && (
        <Section title="Projects">
          <div className="space-y-3">
            {resume.projects.map((p, i) => (
              <div key={i}>
                <Entry left={p.name} right={p.details} />
                <Bullets items={p.bullets} highlight={hl} />
              </div>
            ))}
          </div>
        </Section>
      )}

      {resume.education.length > 0 && (
        <Section title="Education">
          <div className="space-y-2">
            {resume.education.map((e, i) => (
              <div key={i}>
                <Entry left={[e.degree, e.institution].filter(Boolean).join(", ")} right={e.dates} />
                {e.details && <p className="text-slate-600">{e.details}</p>}
              </div>
            ))}
          </div>
        </Section>
      )}

      {resume.extra_sections
        .filter((s) => s.items.length)
        .map((s, i) => (
          <Section key={i} title={s.title}>
            <Bullets items={s.items} highlight={hl} />
          </Section>
        ))}
    </article>
  );
}
