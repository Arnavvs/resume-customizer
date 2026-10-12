// Mirrors backend/app/schemas.py

export interface SkillGroup {
  category: string;
  skills: string[];
}

export interface ExperienceItem {
  title: string;
  company: string;
  location: string;
  dates: string;
  bullets: string[];
}

export interface ProjectItem {
  name: string;
  details: string;
  url: string;
  bullets: string[];
}

export interface EducationItem {
  degree: string;
  institution: string;
  dates: string;
  details: string;
}

export interface ExtraSection {
  title: string;
  items: string[];
}

export interface ContactItem {
  text: string;
  url: string;
}

export interface Resume {
  name: string;
  headline: string;
  contact: ContactItem[];
  summary: string;
  skills: SkillGroup[];
  experience: ExperienceItem[];
  projects: ProjectItem[];
  education: EducationItem[];
  extra_sections: ExtraSection[];
}

export interface ParsedResume {
  filename: string;
  size_bytes: number;
  text: string;
  resume: Resume;
}

export type Section = "summary" | "skills" | "experience" | "projects";
export type Intensity = "conservative" | "balanced" | "bold";
export type PageTarget = "auto" | "one" | "two";
export type CoverLetterTone = "professional" | "enthusiastic" | "concise";

export interface MissingKeyword {
  keyword: string;
  importance: "high" | "medium" | "low";
  suggestion: string;
}

export interface ScoreCheck {
  label: string;
  passed: boolean;
  detail: string;
  points: number;
  max_points: number;
}

export interface AtsReport {
  score: number;
  checks: ScoreCheck[];
}

export interface KeywordMatch {
  score: number;
  matched: string[];
  missing: string[];
}

export interface TailorResult {
  target_role: string;
  jd_keywords: string[];
  resume: Resume;
  matched_skills: string[];
  missing_keywords: MissingKeyword[];
  change_log: string[];
  sections: Section[];
  intensity: Intensity;
  page_target: PageTarget;
  page_count: number;
  scores: {
    match_before: KeywordMatch;
    match_after: KeywordMatch;
    ats_before: AtsReport;
    ats_after: AtsReport;
  };
}

/** A generated version kept on the client so users can compare several tailorings. */
export interface ResumeVersion extends TailorResult {
  id: string;
  label: string;
  createdAt: number;
  jobDescription: string;
}
