import type { Intensity, Section } from "@/lib/types";
import { cn } from "@/lib/utils";
import { StepLabel } from "./ui";

export const ALL_SECTIONS: { id: Section; label: string }[] = [
  { id: "summary", label: "Summary" },
  { id: "skills", label: "Skills" },
  { id: "experience", label: "Experience" },
  { id: "projects", label: "Projects" },
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
}: {
  sections: Section[];
  onSectionsChange: (s: Section[]) => void;
  intensity: Intensity;
  onIntensityChange: (i: Intensity) => void;
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
        <div className="grid grid-cols-3 gap-1 rounded-xl bg-slate-100 p-1" role="radiogroup">
          {INTENSITIES.map(({ id, label, hint }) => (
            <button
              key={id}
              type="button"
              role="radio"
              aria-checked={intensity === id}
              title={hint}
              onClick={() => onIntensityChange(id)}
              className={cn(
                "rounded-lg py-1.5 text-sm font-medium transition",
                intensity === id ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="mt-1.5 text-xs text-slate-400">{INTENSITIES.find((i) => i.id === intensity)?.hint}</p>
      </fieldset>
    </div>
  );
}
