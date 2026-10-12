import { cn } from "@/lib/utils";
import { StepLabel } from "./ui";

export const JD_MIN = 100;
export const JD_MAX = 20000;

export function jdError(value: string): string | null {
  const len = value.trim().length;
  if (len === 0) return "Paste the job description to continue.";
  if (len < JD_MIN) return `That looks too short for a job description (${len}/${JD_MIN} characters minimum).`;
  if (len > JD_MAX) return `Job description is too long (${len.toLocaleString()}/${JD_MAX.toLocaleString()} characters).`;
  return null;
}

export function JobDescriptionInput({
  value,
  onChange,
  showError,
}: {
  value: string;
  onChange: (v: string) => void;
  showError: boolean;
}) {
  const error = jdError(value);
  const len = value.trim().length;
  return (
    <div className="space-y-2">
      <StepLabel n={1}>Job description</StepLabel>
      <textarea
        id="jd"
        aria-label="Job description"
        aria-invalid={showError && !!error}
        aria-describedby="jd-help"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Paste the full job posting here — responsibilities, requirements, nice-to-haves…"
        className={cn(
          "h-48 w-full resize-y rounded-xl border bg-slate-50/60 p-3 text-sm leading-relaxed text-slate-800 outline-none transition",
          "placeholder:text-slate-400 focus:border-indigo-400 focus:bg-white focus:ring-4 focus:ring-indigo-100",
          showError && error ? "border-red-300" : "border-slate-200",
        )}
      />
      <div id="jd-help" className="flex justify-between text-xs">
        <span className={cn(showError && error ? "text-red-600" : "text-slate-400")}>
          {showError && error ? error : "Tip: include the requirements section — that's where the keywords are."}
        </span>
        <span className={cn("tabular-nums", len > JD_MAX ? "text-red-600" : "text-slate-400")}>
          {len.toLocaleString()} chars
        </span>
      </div>
    </div>
  );
}
