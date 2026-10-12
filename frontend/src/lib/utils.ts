import type { Resume } from "./types";

export function cn(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function safeFileName(name: string): string {
  return name.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_|_$/g, "") || "resume";
}

/** Plain-text rendering of a resume (same layout as the backend's resume_to_text). */
export function resumeToText(r: Resume): string {
  const lines: string[] = [r.name];
  if (r.headline) lines.push(r.headline);
  if (r.contact.length) lines.push(r.contact.join(" | "));
  if (r.summary) lines.push("", "SUMMARY", r.summary);
  if (r.skills.length) {
    lines.push("", "SKILLS");
    r.skills.forEach((g) => lines.push(g.category ? `${g.category}: ${g.skills.join(", ")}` : g.skills.join(", ")));
  }
  if (r.experience.length) {
    lines.push("", "EXPERIENCE");
    r.experience.forEach((j) => {
      const meta = [j.location, j.dates].filter(Boolean).join(" | ");
      lines.push(`${[j.title, j.company].filter(Boolean).join(" — ")}${meta ? ` (${meta})` : ""}`);
      j.bullets.forEach((b) => lines.push(`• ${b}`));
    });
  }
  if (r.projects.length) {
    lines.push("", "PROJECTS");
    r.projects.forEach((p) => {
      lines.push(`${p.name}${p.details ? ` — ${p.details}` : ""}`);
      p.bullets.forEach((b) => lines.push(`• ${b}`));
    });
  }
  if (r.education.length) {
    lines.push("", "EDUCATION");
    r.education.forEach((e) => {
      lines.push(`${[e.degree, e.institution].filter(Boolean).join(", ")}${e.dates ? ` (${e.dates})` : ""}`);
      if (e.details) lines.push(e.details);
    });
  }
  r.extra_sections.forEach((s) => {
    lines.push("", s.title.toUpperCase());
    s.items.forEach((i) => lines.push(`• ${i}`));
  });
  return lines.join("\n").trim();
}

/** localStorage wrapper that never throws (private mode, quota, disabled storage). */
export const storage = {
  get<T>(key: string): T | null {
    try {
      const raw = window.localStorage.getItem(key);
      return raw ? (JSON.parse(raw) as T) : null;
    } catch {
      return null;
    }
  },
  set(key: string, value: unknown): void {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* ignore */
    }
  },
  remove(key: string): void {
    try {
      window.localStorage.removeItem(key);
    } catch {
      /* ignore */
    }
  },
};
