import { Fragment, type ReactNode } from "react";
import type { Resume } from "@/lib/types";
import { cn } from "@/lib/utils";

// Mirrors backend/app/export.py so what you see is what you download.

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-[1.1em] first:mt-0">
      <h3 className="mb-[0.55em] border-b border-[#c4cede] pb-[0.2em] text-[0.95em] font-bold uppercase tracking-[0.12em] text-[#1e4078]">
        {title}
      </h3>
      {children}
    </section>
  );
}

function Entry({ children, right }: { children: ReactNode; right?: string }) {
  return (
    <div className="mt-[0.5em] flex items-baseline justify-between gap-x-4 first:mt-0">
      <p className="min-w-0">{children}</p>
      {right && <p className="shrink-0 text-[0.86em] italic text-[#646e7d]">{right}</p>}
    </div>
  );
}

function Bullets({ items, highlight }: { items: string[]; highlight: (t: string) => ReactNode }) {
  return (
    <ul className="mt-[0.15em] space-y-[0.15em]">
      {items.map((b, i) => (
        <li key={i} className="relative pl-[1.15em]">
          <span className="absolute left-[0.2em] text-[#1e4078]" aria-hidden>
            •
          </span>
          {highlight(b)}
        </li>
      ))}
    </ul>
  );
}

function ExternalLink({ href, className, children }: { href: string; className?: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target={href.startsWith("http") ? "_blank" : undefined}
      rel="noopener noreferrer"
      className={cn("text-[#1e4078] decoration-[#1e4078]/40 underline-offset-2 hover:underline", className)}
    >
      {children}
    </a>
  );
}

/** Wraps occurrences of the given keywords in <mark>. */
function makeHighlighter(keywords: string[]) {
  const terms = keywords.filter((k) => k.trim().length > 1).sort((a, b) => b.length - a.length);
  if (!terms.length) return (t: string) => t;
  const escaped = terms.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const re = new RegExp(`(?<![A-Za-z0-9])(${escaped.join("|")})(?![A-Za-z0-9+#])`, "gi");
  return (text: string): ReactNode =>
    text.split(re).map((part, i) =>
      i % 2 === 1 ? (
        <mark key={i} className="rounded-sm bg-amber-100 px-0.5 text-inherit">
          {part}
        </mark>
      ) : (
        part
      ),
    );
}

const fold = (text: string) => text.replace(/[ \t]*\n[ \t]*-?[ \t]*/g, " — ");

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
  const contact = resume.contact.filter((c) => c.text.trim());
  return (
    <article
      className={cn(
        "mx-auto max-w-[820px] rounded-md bg-white font-[family-name:var(--font-resume)] leading-[1.42] text-[#2d3748]",
        "shadow-[0_1px_3px_rgba(15,23,42,.08),0_12px_32px_rgba(15,23,42,.08)] ring-1 ring-slate-200",
        compact ? "p-5 text-[11.5px]" : "px-5 py-7 text-[13px] sm:px-12 sm:py-11 sm:text-[13.5px]",
      )}
    >
      <header className="mb-[1.1em] text-center">
        <h2 className="text-[2.15em] font-bold leading-tight tracking-[0.02em] text-[#111827]">{resume.name}</h2>
        {resume.headline && <p className="mt-[0.15em] text-[1.05em] text-[#1e4078]">{resume.headline}</p>}
        {contact.length > 0 && (
          <p className="mt-[0.35em] text-[0.88em] text-[#646e7d]">
            {contact.map((c, i) => (
              <Fragment key={i}>
                {i > 0 && (
                  <span className="mx-[0.7em] text-[#c4cede]" aria-hidden>
                    •
                  </span>
                )}
                <span className="whitespace-nowrap">
                  {c.url ? <ExternalLink href={c.url}>{c.text}</ExternalLink> : c.text}
                </span>
              </Fragment>
            ))}
          </p>
        )}
      </header>

      {resume.summary && (
        <Section title="Summary">
          <p>{hl(resume.summary)}</p>
        </Section>
      )}

      {resume.skills.length > 0 && (
        <Section title="Skills">
          <div className="space-y-[0.2em]">
            {resume.skills.map((g, i) => (
              <p key={i}>
                {g.category && <span className="font-bold text-[#111827]">{g.category}: </span>}
                {hl(g.skills.join(", "))}
              </p>
            ))}
          </div>
        </Section>
      )}

      {resume.experience.length > 0 && (
        <Section title="Experience">
          {resume.experience.map((job, i) => (
            <div key={i}>
              <Entry right={[job.location, job.dates].filter(Boolean).join("  |  ")}>
                <span className="font-bold text-[#111827]">{job.title}</span>
                {job.company && <span className="text-[0.95em]"> · {job.company}</span>}
              </Entry>
              <Bullets items={job.bullets} highlight={hl} />
            </div>
          ))}
        </Section>
      )}

      {resume.projects.length > 0 && (
        <Section title="Projects">
          {resume.projects.map((p, i) => (
            <div key={i}>
              <Entry>
                {p.url ? (
                  <ExternalLink href={p.url} className="font-bold">
                    {p.name}
                  </ExternalLink>
                ) : (
                  <span className="font-bold text-[#111827]">{p.name}</span>
                )}
                {p.details && <span className="text-[0.92em] italic text-[#646e7d]"> · {p.details}</span>}
              </Entry>
              <Bullets items={p.bullets} highlight={hl} />
            </div>
          ))}
        </Section>
      )}

      {resume.education.length > 0 && (
        <Section title="Education">
          {resume.education.map((e, i) => (
            <div key={i}>
              <Entry right={e.dates}>
                <span className="font-bold text-[#111827]">{e.degree}</span>
                {e.institution && <span className="text-[0.95em]"> · {e.institution}</span>}
              </Entry>
              {e.details && <p className="text-[0.94em] text-[#646e7d]">{e.details}</p>}
            </div>
          ))}
        </Section>
      )}

      {resume.extra_sections
        .filter((s) => s.items.length)
        .map((s, i) => (
          <Section key={i} title={s.title}>
            <Bullets items={s.items.map(fold)} highlight={hl} />
          </Section>
        ))}
    </article>
  );
}
