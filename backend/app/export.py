"""Render a structured Resume to ATS-friendly DOCX and PDF files (single column, no tables)."""

import io
import re
import unicodedata
from collections.abc import Callable

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from fpdf import FPDF
from fpdf.enums import XPos, YPos

from .schemas import Resume

ACCENT = (31, 64, 104)


def _sections(resume: Resume) -> list[tuple[str, Callable[["_Writer"], None]]]:
    """Section order and content shared by both renderers."""
    out: list[tuple[str, Callable[[_Writer], None]]] = []
    if resume.summary:
        out.append(("Summary", lambda w: w.paragraph(resume.summary)))
    if resume.skills:
        def skills(w: _Writer) -> None:
            for g in resume.skills:
                w.labelled(g.category, ", ".join(g.skills))
        out.append(("Skills", skills))
    if resume.experience:
        def experience(w: _Writer) -> None:
            for job in resume.experience:
                w.entry(" — ".join(p for p in (job.title, job.company) if p),
                        " | ".join(p for p in (job.location, job.dates) if p))
                for b in job.bullets:
                    w.bullet(b)
        out.append(("Experience", experience))
    if resume.projects:
        def projects(w: _Writer) -> None:
            for proj in resume.projects:
                w.entry(proj.name, proj.details)
                for b in proj.bullets:
                    w.bullet(b)
        out.append(("Projects", projects))
    if resume.education:
        def education(w: _Writer) -> None:
            for edu in resume.education:
                w.entry(", ".join(p for p in (edu.degree, edu.institution) if p), edu.dates)
                if edu.details:
                    w.paragraph(edu.details)
        out.append(("Education", education))
    for extra in resume.extra_sections:
        if extra.items:
            out.append((extra.title, _bullet_list(extra.items)))
    return out


def _bullet_list(items: list[str]) -> Callable[["_Writer"], None]:
    def render(w: _Writer) -> None:
        for item in items:
            w.bullet(item)
    return render


class _Writer:
    def paragraph(self, text: str) -> None: ...
    def labelled(self, label: str, text: str) -> None: ...
    def entry(self, left: str, right: str) -> None: ...
    def bullet(self, text: str) -> None: ...


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------


class _DocxWriter(_Writer):
    def __init__(self, doc: Document):
        self.doc = doc

    def _p(self, space_after: float = 2):
        p = self.doc.add_paragraph()
        p.paragraph_format.space_after = Pt(space_after)
        p.paragraph_format.space_before = Pt(0)
        return p

    def heading(self, title: str) -> None:
        p = self._p(3)
        p.paragraph_format.space_before = Pt(10)
        run = p.add_run(title.upper())
        run.bold, run.font.size, run.font.color.rgb = True, Pt(11), RGBColor(*ACCENT)
        # bottom border under the section heading
        border = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        for k, v in {"w:val": "single", "w:sz": "6", "w:space": "1", "w:color": "1F4068"}.items():
            bottom.set(qn(k), v)
        border.append(bottom)
        p._p.get_or_add_pPr().append(border)

    def paragraph(self, text: str) -> None:
        self._p(4).add_run(text)

    def labelled(self, label: str, text: str) -> None:
        p = self._p()
        if label:
            p.add_run(f"{label}: ").bold = True
        p.add_run(text)

    def entry(self, left: str, right: str) -> None:
        p = self._p(1)
        p.paragraph_format.space_before = Pt(4)
        p.add_run(left).bold = True
        if right:
            p.add_run(f"   {right}").italic = True

    def bullet(self, text: str) -> None:
        p = self.doc.add_paragraph(text, style="List Bullet")
        p.paragraph_format.space_after = Pt(1)


def to_docx(resume: Resume) -> bytes:
    doc = Document()
    for section in doc.sections:
        section.top_margin = section.bottom_margin = Pt(42)
        section.left_margin = section.right_margin = Pt(50)
    normal = doc.styles["Normal"]
    normal.font.name, normal.font.size = "Calibri", Pt(10.5)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run(resume.name)
    run.bold, run.font.size = True, Pt(20)
    title.paragraph_format.space_after = Pt(0)
    for line in (resume.headline, " | ".join(resume.contact)):
        if line:
            p = doc.add_paragraph(line)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(0)

    writer = _DocxWriter(doc)
    for heading, render in _sections(resume):
        writer.heading(heading)
        render(writer)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

_PDF_REPLACEMENTS = {
    "‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
    "•": "-", "…": "...", " ": " ", "→": "->", "−": "-", "₹": "Rs.",
    "™": "(TM)", "≥": ">=", "≤": "<=",
}


def _latin1(text: str) -> str:
    """fpdf2's built-in fonts are Latin-1; map common typography and strip what can't be shown."""
    text = "".join(_PDF_REPLACEMENTS.get(ch, ch) for ch in text)
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"[^\x00-\xff]", "", text)


class _PdfWriter(_Writer):
    def __init__(self, pdf: FPDF):
        self.pdf = pdf

    def heading(self, title: str) -> None:
        pdf = self.pdf
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*ACCENT)
        pdf.cell(0, 6, _latin1(title.upper()), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_draw_color(*ACCENT)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(1.5)
        pdf.set_text_color(20, 20, 20)

    def paragraph(self, text: str) -> None:
        self.pdf.set_font("Helvetica", "", 10)
        self.pdf.multi_cell(0, 4.8, _latin1(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.pdf.ln(0.8)

    def labelled(self, label: str, text: str) -> None:
        pdf = self.pdf
        pdf.set_x(pdf.l_margin)
        if label:
            pdf.set_font("Helvetica", "B", 10)
            pdf.write(4.8, f"{_latin1(label)}: ")
        pdf.set_font("Helvetica", "", 10)
        pdf.write(4.8, _latin1(text))
        pdf.ln(5.2)

    def entry(self, left: str, right: str) -> None:
        pdf = self.pdf
        pdf.ln(1.2)
        pdf.set_font("Helvetica", "I", 9.5)
        right = _latin1(right)
        right_w = pdf.get_string_width(right) + 1 if right else 0
        pdf.set_font("Helvetica", "B", 10.5)
        y = pdf.get_y()
        pdf.multi_cell(pdf.epw - right_w - 2, 5.2, _latin1(left), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if right:
            end_y = pdf.get_y()
            pdf.set_xy(pdf.w - pdf.r_margin - right_w, y)
            pdf.set_font("Helvetica", "I", 9.5)
            pdf.cell(right_w, 5.2, right, align="R")
            pdf.set_xy(pdf.l_margin, end_y)

    def bullet(self, text: str) -> None:
        pdf = self.pdf
        pdf.set_font("Helvetica", "", 10)
        indent = 4.5
        pdf.set_x(pdf.l_margin + 1)
        pdf.cell(indent - 1, 4.8, chr(149))  # Latin-1 / cp1252 bullet
        pdf.multi_cell(pdf.epw - indent, 4.8, _latin1(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(0.4)


def to_pdf(resume: Resume) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_margins(16, 14, 16)
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.set_title(_latin1(f"{resume.name} - Resume"))
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 9, _latin1(resume.name), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    for line in (resume.headline, " | ".join(resume.contact)):
        if line:
            pdf.multi_cell(0, 5, _latin1(line), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    writer = _PdfWriter(pdf)
    for heading, render in _sections(resume):
        writer.heading(heading)
        render(writer)
    return bytes(pdf.output())
