"use client";

import { useState } from "react";
import type { ResumeVersion } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ResumeView } from "./ResumeView";

function VersionSelect({
  versions,
  value,
  onChange,
  label,
}: {
  versions: ResumeVersion[];
  value: string;
  onChange: (id: string) => void;
  label: string;
}) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="sr-only">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm font-medium text-slate-800 outline-none focus:ring-2 focus:ring-indigo-200"
      >
        {versions.map((v) => (
          <option key={v.id} value={v.id}>
            {v.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function Stat({ label, a, b }: { label: string; a: number; b: number }) {
  const better = (x: number, y: number) => (x > y ? "font-semibold text-emerald-600" : "text-slate-600");
  return (
    <div className="flex items-center justify-between border-b border-slate-100 py-1.5 text-sm last:border-0">
      <span className={cn("w-12 tabular-nums", better(a, b))}>{a}%</span>
      <span className="text-xs text-slate-500">{label}</span>
      <span className={cn("w-12 text-right tabular-nums", better(b, a))}>{b}%</span>
    </div>
  );
}

export function CompareView({ versions }: { versions: ResumeVersion[] }) {
  const [leftId, setLeftId] = useState(versions[versions.length - 2]?.id ?? versions[0].id);
  const [rightId, setRightId] = useState(versions[versions.length - 1].id);
  const left = versions.find((v) => v.id === leftId) ?? versions[0];
  const right = versions.find((v) => v.id === rightId) ?? versions[versions.length - 1];

  if (versions.length < 2) {
    return (
      <div className="rounded-xl border border-dashed border-slate-200 bg-white/60 px-6 py-12 text-center text-sm text-slate-500">
        Generate another version (e.g. with a different intensity or set of sections) to compare them side by side.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="grid grid-cols-2 gap-3">
          <VersionSelect versions={versions} value={left.id} onChange={setLeftId} label="Left version" />
          <VersionSelect versions={versions} value={right.id} onChange={setRightId} label="Right version" />
        </div>
        <div className="mt-3">
          <Stat label="JD keyword match" a={left.scores.match_after.score} b={right.scores.match_after.score} />
          <Stat label="ATS readiness" a={left.scores.ats_after.score} b={right.scores.ats_after.score} />
        </div>
      </div>
      <div className="grid gap-3 xl:grid-cols-2">
        <ResumeView resume={left.resume} keywords={left.scores.match_after.matched} compact />
        <ResumeView resume={right.resume} keywords={right.scores.match_after.matched} compact />
      </div>
    </div>
  );
}
