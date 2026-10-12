"""Deterministic scores, so the numbers shown to users are explainable and reproducible.

* Keyword match: share of the JD's key terms (extracted by the LLM) that literally appear in a
  resume. Computed for the original and the tailored resume with the same keyword list.
* ATS score: a transparent checklist of common ATS / recruiter heuristics.
"""

import re

from .schemas import AtsReport, KeywordMatch, Resume, ScoreCheck

ACTION_VERBS = {
    "accelerated", "achieved", "analyzed", "analysed", "architected", "automated", "built", "championed",
    "collaborated", "configured", "consolidated", "contributed", "coordinated", "created", "cut", "decreased",
    "defined", "delivered", "deployed", "designed", "developed", "devised", "directed", "drove", "enabled",
    "engineered", "enhanced", "established", "evaluated", "executed", "expanded", "facilitated", "founded",
    "generated", "grew", "guided", "headed", "identified", "implemented", "improved", "increased", "initiated",
    "integrated", "introduced", "launched", "led", "maintained", "managed", "mentored", "migrated", "modernized",
    "monitored", "negotiated", "optimized", "optimised", "orchestrated", "organized", "overhauled", "owned",
    "partnered", "performed", "pioneered", "planned", "presented", "prototyped", "published", "raised",
    "redesigned", "reduced", "refactored", "resolved", "restructured", "revamped", "saved", "scaled",
    "secured", "shipped", "simplified", "spearheaded", "standardized", "streamlined", "strengthened",
    "supervised", "supported", "taught", "tested", "trained", "transformed", "troubleshot", "unified",
    "upgraded", "won", "wrote",
    # present tense, for current roles
    "build", "lead", "manage", "develop", "design", "own", "drive", "maintain", "deliver", "architect",
    "implement", "mentor", "collaborate", "optimize", "automate", "deploy", "partner", "support",
}

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_NUMBER = re.compile(r"\d|%|\$|€|£|₹")


def resume_to_text(resume: Resume) -> str:
    """Plain-text rendering, used for keyword matching and the .txt download."""
    lines: list[str] = [resume.name]
    if resume.headline:
        lines.append(resume.headline)
    if resume.contact:
        lines.append(" | ".join(resume.contact))
    if resume.summary:
        lines += ["", "SUMMARY", resume.summary]
    if resume.skills:
        lines += ["", "SKILLS"]
        lines += [f"{g.category}: {', '.join(g.skills)}" if g.category else ", ".join(g.skills) for g in resume.skills]
    if resume.experience:
        lines += ["", "EXPERIENCE"]
        for job in resume.experience:
            header = " — ".join(p for p in (job.title, job.company) if p)
            meta = " | ".join(p for p in (job.location, job.dates) if p)
            lines.append(f"{header}{f' ({meta})' if meta else ''}")
            lines += [f"• {b}" for b in job.bullets]
    if resume.projects:
        lines += ["", "PROJECTS"]
        for proj in resume.projects:
            lines.append(f"{proj.name}{f' — {proj.details}' if proj.details else ''}")
            lines += [f"• {b}" for b in proj.bullets]
    if resume.education:
        lines += ["", "EDUCATION"]
        for edu in resume.education:
            line = ", ".join(p for p in (edu.degree, edu.institution) if p)
            lines.append(f"{line}{f' ({edu.dates})' if edu.dates else ''}")
            if edu.details:
                lines.append(edu.details)
    for section in resume.extra_sections:
        lines += ["", section.title.upper()]
        lines += [f"• {item}" for item in section.items]
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Keyword match
# ---------------------------------------------------------------------------


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def _keyword_variants(keyword: str) -> list[str]:
    kw = _norm(keyword).strip()
    variants = {kw}
    for suffix in (".js", "js"):
        if kw.endswith(suffix) and len(kw) > len(suffix) + 1:
            variants.add(kw[: -len(suffix)].strip())
    if kw.endswith("s") and len(kw) > 3:
        variants.add(kw[:-1])
    # "CI/CD" vs "CI CD", "front-end" vs "frontend"
    variants.add(re.sub(r"[/\-]", " ", kw))
    variants.add(re.sub(r"[/\-\s]", "", kw))
    # "Amazon Web Services (AWS)" -> also match "AWS"
    if m := re.search(r"\(([^)]+)\)", kw):
        variants.add(m.group(1).strip())
        variants.add(re.sub(r"\s*\([^)]*\)", "", kw).strip())
    return [v for v in variants if v]


def contains_keyword(text: str, keyword: str) -> bool:
    haystack = _norm(text)
    for variant in _keyword_variants(keyword):
        # Custom boundaries so "C++", "C#" and ".NET" work, and "Java" doesn't match "JavaScript".
        pattern = rf"(?<![a-z0-9]){re.escape(variant)}(?![a-z0-9+#])"
        if re.search(pattern, haystack):
            return True
    return False


def keyword_match(text: str, keywords: list[str]) -> KeywordMatch:
    by_lower: dict[str, str] = {}
    for k in keywords:
        by_lower.setdefault(k.strip().lower(), k.strip())
    unique = [k for low, k in by_lower.items() if low]
    if not unique:
        return KeywordMatch(score=0, matched=[], missing=[])
    matched = [k for k in unique if contains_keyword(text, k)]
    missing = [k for k in unique if k not in matched]
    return KeywordMatch(score=round(100 * len(matched) / len(unique)), matched=matched, missing=missing)


# ---------------------------------------------------------------------------
# ATS heuristics
# ---------------------------------------------------------------------------


def _check(label: str, max_points: float, ratio: float, detail: str) -> ScoreCheck:
    ratio = max(0.0, min(1.0, ratio))
    return ScoreCheck(
        label=label, passed=ratio >= 0.7, detail=detail, points=round(max_points * ratio, 1), max_points=max_points
    )


def ats_report(resume: Resume, match: KeywordMatch) -> AtsReport:
    contact = " ".join(resume.contact)
    bullets = [b for job in resume.experience for b in job.bullets] + [b for p in resume.projects for b in p.bullets]
    n_bullets = len(bullets) or 1
    skills = [s for g in resume.skills for s in g.skills]
    summary_words = len(resume.summary.split())

    has_email, has_phone = bool(_EMAIL.search(contact)), bool(_PHONE.search(contact))
    action = sum(1 for b in bullets if (b.split() or [""])[0].lower().strip(",.") in ACTION_VERBS)
    quantified = sum(1 for b in bullets if _NUMBER.search(b))
    good_length = sum(1 for b in bullets if 8 <= len(b.split()) <= 35)

    checks = [
        _check("Keyword coverage", 30, match.score / 100,
               f"{len(match.matched)} of {len(match.matched) + len(match.missing)} key JD terms found"),
        _check("Contact details", 10, (has_email + has_phone) / 2,
               "Email and phone found" if has_email and has_phone else "Add both an email address and a phone number"),
        _check("Professional summary", 10, 1.0 if 25 <= summary_words <= 90 else 0.5 if summary_words else 0.0,
               f"{summary_words} words (aim for 25–90)" if summary_words else "No summary section"),
        _check("Skills section", 10, min(len(skills) / 8, 1.0), f"{len(skills)} skills listed (aim for 8+)"),
        _check("Standard sections", 10, (bool(resume.experience or resume.projects) + bool(resume.education)) / 2,
               "Experience/projects and education present"
               if (resume.experience or resume.projects) and resume.education
               else "ATS parsers expect Experience and Education sections"),
        _check("Action-verb bullets", 10, (action / n_bullets) / 0.8,
               f"{action} of {len(bullets)} bullets start with a strong action verb"),
        _check("Quantified impact", 10, (quantified / n_bullets) / 0.4,
               f"{quantified} of {len(bullets)} bullets include numbers or metrics (aim for 40%+)"),
        _check("Concise bullets", 10, (good_length / n_bullets) / 0.85,
               f"{good_length} of {len(bullets)} bullets are 8–35 words"),
    ]
    if not bullets:
        for c in checks[5:]:
            c.points, c.passed, c.detail = 0.0, False, "No experience or project bullets found"
    return AtsReport(score=round(sum(c.points for c in checks)), checks=checks)
