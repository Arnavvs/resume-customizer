import type { Intensity, PageTarget, Section } from "@/lib/types";
import { cn } from "@/lib/utils";
import { StepLabel } from "./ui";

function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { id: T; label: string; hint: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="grid grid-cols-3 gap-1 rounded-xl bg-slate-100 p-1" role="radiogroup">
      {options.map(({ id, label, hint }) => (
        <button
          key={id}
          type="button"
          role="radio"
          aria-checked={value === id}
          title={hint}
          onClick={() => onChange(id)}
          className={cn(
            "rounded-lg py-1.5 text-sm font-medium transition",
            value === id ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800",
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export const ALL_SECTIONS: { id: Section; label: string }[] = [
  { id: "summary", label: "Summary" },
  { id: "skills", label: "Skills" },
  { id: "experience", label: "Experience" },
  { id: "projects", label: "Projects" },
];

const PAGE_TARGETS: { id: PageTarget; label: string; hint: string }[] = [
  { id: "one", label: "1 page", hint: "Condensed to the most relevant content — best for < 5 years' experience" },
  { id: "two", label: "2 pages", hint: "Room for all relevant experience and projects" },
  { id: "auto", label: "Auto", hint: "Keep roughly your original length" },
];

const INTENSITIES: { id: Intensity; label: string; hint: string }[] = [
  { id: "conservative", label: "Light", hint: "Keep my wording, reorder & add JD terms" },
  { id: "balanced", label: "Balanced", hint: "Rewrite for clarity and alignment" },
  { id: "bold", label: "Bold", hint: "Aggressively reframe for this role" },
];

export function TailorOptions({
  sections,
  onSectionsChange,
  intensity,
  onIntensityChange,
  pageTarget,
  onPageTargetChange,
}: {
  sections: Section[];
  onSectionsChange: (s: Section[]) => void;
  intensity: Intensity;
  onIntensityChange: (i: Intensity) => void;
  pageTarget: PageTarget;
  onPageTargetChange: (p: PageTarget) => void;
}) {
  const toggle = (id: Section) =>
    onSectionsChange(sections.includes(id) ? sections.filter((s) => s !== id) : [...sections, id]);

  return (
    <div className="space-y-3">
      <StepLabel n={3}>Customization</StepLabel>
      <fieldset>
        <legend className="mb-1.5 text-xs font-medium text-slate-500">Sections to tailor</legend>
        <div className="flex flex-wrap gap-2">
          {ALL_SECTIONS.map(({ id, label }) => {
            const on = sections.includes(id);
            return (
              <button
                key={id}
                type="button"
                role="checkbox"
                aria-checked={on}
                onClick={() => toggle(id)}
                className={cn(
                  "rounded-full px-3 py-1 text-sm font-medium ring-1 transition",
                  on ? "bg-indigo-600 text-white ring-indigo-600" : "bg-white text-slate-600 ring-slate-200 hover:ring-slate-300",
                )}
              >
                {label}
              </button>
            );
          })}
        </div>
        {sections.length === 0 && <p className="mt-1.5 text-xs text-red-600">Select at least one section.</p>}
      </fieldset>
      <fieldset>
        <legend className="mb-1.5 text-xs font-medium text-slate-500">Editing intensity</legend>
        <Segmented options={INTENSITIES} value={intensity} onChange={onIntensityChange} />
        <p className="mt-1.5 text-xs text-slate-400">{INTENSITIES.find((i) => i.id === intensity)?.hint}</p>
      </fieldset>
      <fieldset>
        <legend className="mb-1.5 text-xs font-medium text-slate-500">Resume length</legend>
        <Segmented options={PAGE_TARGETS} value={pageTarget} onChange={onPageTargetChange} />
        <p className="mt-1.5 text-xs text-slate-400">{PAGE_TARGETS.find((p) => p.id === pageTarget)?.hint}</p>
      </fieldset>
    </div>
  );
}
