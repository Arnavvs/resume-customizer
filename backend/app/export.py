"""Render a structured Resume to ATS-friendly PDF and DOCX files.

Layout rules shared by both formats: single column, no tables or text boxes (ATS parsers read
them poorly), left-aligned text, dates right-aligned on the entry line, real clickable links.

The PDF renderer can "fit to pages": it re-renders at slightly smaller type and spacing until the
resume fits the requested page count (down to MIN_SCALE, which keeps body text >= ~8.5pt).
"""

import io
import re
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor
from fpdf import FPDF
from fpdf.enums import XPos, YPos

from .schemas import ContactItem, Resume

FONT_DIR = Path(__file__).parent / "fonts"
FONT = "Lato"

INK = (17, 24, 39)
BODY = (45, 55, 72)
MUTED = (100, 110, 125)
ACCENT = (30, 64, 120)
RULE = (196, 206, 222)

PAGE_TARGETS = {"one": 1, "two": 2}
SCALES = (1.0, 0.96, 0.92, 0.885, 0.85)
MIN_SCALE = SCALES[-1]


def clean(text: str) -> str:
    """Fold internal line breaks (LLM output sometimes contains them) into an em-dash join."""
    return re.sub(r"[ \t]*\n[ \t]*-?[ \t]*", " — ", text.strip("\n"))


def contact_url(item: ContactItem) -> str:
    """Best link target for a contact item, deriving one when the parser left it empty."""
    if item.url:
        return item.url
    text = item.text.strip()
    if re.fullmatch(r"[\w.+-]+@[\w-]+\.[\w.-]+", text):
        return f"mailto:{text}"
    if re.fullmatch(r"\+?[\d\s().-]{8,}", text):
        return "tel:" + re.sub(r"[^\d+]", "", text)
    if re.match(r"(https?://)?([\w-]+\.)+[a-z]{2,}(/\S*)?$", text, re.I) and "@" not in text:
        return text if text.startswith("http") else f"https://{text}"
    return ""


@dataclass
class PdfResult:
    content: bytes
    pages: int
    scale: float


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


class _ResumePDF(FPDF):
    def __init__(self, scale: float):
        super().__init__(format="A4", unit="mm")
        self.s = scale
        for style, suffix in (("", "Regular"), ("B", "Bold"), ("I", "Italic"), ("BI", "BoldItalic")):
            self.add_font(FONT, style, str(FONT_DIR / f"Lato-{suffix}.ttf"))
        side = 12 + 4 * scale  # 16mm at full scale, ~15.4mm at min
        self.set_margins(side, 10 + 4 * scale, side)
        self.set_auto_page_break(auto=True, margin=10 + 3 * scale)
        self.set_creator("Resume Customizer")

    # -- primitives ---------------------------------------------------------
    def pt(self, size: float) -> float:
        return size * self.s

    def lh(self, size_pt: float, factor: float = 1.32) -> float:
        """Line height in mm for a font size in pt."""
        return self.pt(size_pt) * 0.3528 * factor

    def font(self, style: str, size: float, color: tuple[int, int, int]) -> None:
        self.set_font(FONT, style, self.pt(size))
        self.set_text_color(*color)

    # -- blocks ---------------------------------------------------------------
    def header_block(self, resume: Resume) -> None:
        self.font("B", 22, INK)
        self.set_char_spacing(0.4)
        self.cell(0, self.lh(22, 1.15), clean(resume.name).strip(), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_char_spacing(0)
        if resume.headline:
            self.ln(self.pt(0.6))
            self.font("", 10.5, ACCENT)
            self.multi_cell(0, self.lh(10.5), clean(resume.headline), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if resume.contact:
            self.ln(self.pt(0.8))
            self.contact_line(resume.contact)
        self.ln(self.pt(1.2))

    def contact_line(self, items: list[ContactItem]) -> None:
        size, sep = 9, "   •   "
        self.font("", size, MUTED)
        h = self.lh(size)
        parts = [(clean(i.text), contact_url(i)) for i in items if i.text.strip()]
        # Greedy wrap into centred lines.
        lines: list[list[tuple[str, str]]] = [[]]
        width = 0.0
        sep_w = self.get_string_width(sep)
        for text, url in parts:
            w = self.get_string_width(text)
            if lines[-1] and width + sep_w + w > self.epw:
                lines.append([])
                width = 0.0
            width += (sep_w if lines[-1] else 0) + w
            lines[-1].append((text, url))
        for line in lines:
            total = sum(self.get_string_width(t) for t, _ in line) + sep_w * (len(line) - 1)
            self.set_x(self.l_margin + (self.epw - total) / 2)
            for i, (text, url) in enumerate(line):
                if i:
                    self.set_text_color(*RULE)
                    self.cell(sep_w, h, sep)
                self.set_text_color(*(ACCENT if url else MUTED))
                self.cell(self.get_string_width(text), h, text, link=url or "")
            self.ln(h)

    def section(self, title: str) -> None:
        self.ln(self.pt(3.6))
        # Never leave a heading orphaned: require room for it plus an entry line and two body lines.
        if self.will_page_break(self.lh(10.5, 1.2) + self.pt(5) + self.lh(10.3) * 4):
            self.add_page()
        self.font("B", 10.5, ACCENT)
        self.set_char_spacing(0.9)
        self.cell(0, self.lh(10.5, 1.2), title.upper(), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_char_spacing(0)
        self.set_draw_color(*RULE)
        self.set_line_width(0.3)
        y = self.get_y() + 0.4
        self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.ln(self.pt(2.4))

    def paragraph(self, text: str, size: float = 9.8, color=BODY) -> None:
        self.font("", size, color)
        self.multi_cell(0, self.lh(size), clean(text), align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def labelled(self, label: str, text: str) -> None:
        size = 9.8
        h = self.lh(size)
        self.set_x(self.l_margin)
        if label:
            self.font("B", size, INK)
            self.write(h, f"{clean(label)}: ")
        self.font("", size, BODY)
        self.write(h, clean(text))
        self.ln(h + self.pt(0.7))

    def entry(self, parts: list[tuple[str, str, tuple[int, int, int], str]], right: str) -> None:
        """One entry line: styled left fragments (text, style, colour, link) + right-aligned meta.
        Left text wraps before the right column instead of running underneath it."""
        size = 10.3
        h = self.lh(size)
        if self.will_page_break(h * 3):
            self.add_page()
        self.ln(self.pt(1.6))
        y0 = self.get_y()
        self.font("I", 9, MUTED)
        right = clean(right)
        right_w = self.get_string_width(right) + 1 if right else 0
        old_r = self.r_margin
        self.set_right_margin(old_r + right_w + (3 if right else 0))
        self.set_x(self.l_margin)
        for text, style, color, link in parts:
            if not text:
                continue
            self.font(style, size if style.startswith("B") else size - 0.6, color)
            self.write(h, clean(text), link=link)
        self.ln(h)
        y_end = self.get_y()
        self.set_right_margin(old_r)
        if right:
            self.font("I", 9, MUTED)
            self.set_xy(self.w - old_r - right_w, y0)
            self.cell(right_w, h, right, align="R")
        self.set_xy(self.l_margin, max(y_end, y0 + h))

    def bullet(self, text: str) -> None:
        size = 9.8
        h = self.lh(size)
        indent = 4.2
        self.ln(self.pt(0.5))
        self.font("", size, ACCENT)
        self.set_x(self.l_margin + 0.8)
        self.cell(indent - 0.8, h, "•")
        self.font("", size, BODY)
        self.multi_cell(self.epw - indent, h, clean(text), align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _render_pdf(resume: Resume, scale: float) -> _ResumePDF:
    pdf = _ResumePDF(scale)
    pdf.set_title(f"{resume.name} - Resume")
    pdf.set_author(resume.name)
    pdf.add_page()
    pdf.header_block(resume)

    if resume.summary:
        pdf.section("Summary")
        pdf.paragraph(resume.summary)
    if resume.skills:
        pdf.section("Skills")
        for g in resume.skills:
            pdf.labelled(g.category, ", ".join(g.skills))
    if resume.experience:
        pdf.section("Experience")
        for job in resume.experience:
            pdf.entry(
                [(job.title, "B", INK, ""), (f"  ·  {job.company}" if job.company else "", "", BODY, "")],
                "  |  ".join(p for p in (job.location, job.dates) if p),
            )
            for b in job.bullets:
                pdf.bullet(b)
    if resume.projects:
        pdf.section("Projects")
        for proj in resume.projects:
            pdf.entry(
                [
                    (proj.name, "B", ACCENT if proj.url else INK, proj.url),
                    (f"  ·  {proj.details}" if proj.details else "", "I", MUTED, ""),
                ],
                "",
            )
            for b in proj.bullets:
                pdf.bullet(b)
    if resume.education:
        pdf.section("Education")
        for edu in resume.education:
            pdf.entry(
                [(edu.degree, "B", INK, ""), (f"  ·  {edu.institution}" if edu.institution else "", "", BODY, "")],
                edu.dates,
            )
            if edu.details:
                pdf.ln(pdf.pt(0.4))
                pdf.paragraph(edu.details, size=9.4, color=MUTED)
    for extra in resume.extra_sections:
        if extra.items:
            pdf.section(extra.title)
            for item in extra.items:
                pdf.bullet(item)
    return pdf


def to_pdf(resume: Resume, page_target: str = "auto") -> PdfResult:
    target = PAGE_TARGETS.get(page_target)
    pdf = _render_pdf(resume, 1.0)
    scale = 1.0
    if target is None:
        # Auto: avoid a last page holding only a few lines by tightening slightly.
        last_page_fill = (pdf.get_y() - pdf.t_margin) / (pdf.h - pdf.t_margin - pdf.b_margin)
        if pdf.page_no() > 1 and last_page_fill < 0.2:
            target = pdf.page_no() - 1
    if target is not None:
        for scale in SCALES:
            pdf = _render_pdf(resume, scale) if scale != 1.0 else pdf
            if pdf.page_no() <= target:
                break
    return PdfResult(content=bytes(pdf.output()), pages=pdf.page_no(), scale=scale)


def page_count(resume: Resume, page_target: str = "auto") -> int:
    return to_pdf(resume, page_target).pages


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------


def _rgb(color: tuple[int, int, int]) -> RGBColor:
    return RGBColor(*color)


def _add_hyperlink(paragraph, text: str, url: str, size: float, color=ACCENT, bold=False):
    """python-docx has no public hyperlink API; build the w:hyperlink element directly."""
    rel_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), rel_id)
    run = OxmlElement("w:r")
    props = OxmlElement("w:rPr")
    for tag, val in (("w:color", "%02X%02X%02X" % color), ("w:sz", str(int(size * 2)))):
        el = OxmlElement(tag)
        el.set(qn("w:val"), val)
        props.append(el)
    if bold:
        props.append(OxmlElement("w:b"))
    run.append(props)
    t = OxmlElement("w:t")
    t.text = text
    t.set(qn("xml:space"), "preserve")
    run.append(t)
    link.append(run)
    paragraph._p.append(link)


class _DocxWriter:
    def __init__(self, doc, scale: float):
        self.doc = doc
        self.s = scale
        section = doc.sections[0]
        self.text_width = section.page_width - section.left_margin - section.right_margin

    def pt(self, size: float) -> Pt:
        return Pt(size * self.s)

    def para(self, before: float = 0, after: float = 0, align=None):
        p = self.doc.add_paragraph()
        fmt = p.paragraph_format
        fmt.space_before, fmt.space_after = self.pt(before), self.pt(after)
        fmt.line_spacing = 1.08
        if align is not None:
            p.alignment = align
        return p

    def run(self, p, text: str, size: float, color=BODY, bold=False, italic=False):
        r = p.add_run(clean(text))
        r.font.size, r.font.bold, r.font.italic = self.pt(size), bold, italic
        r.font.color.rgb = _rgb(color)
        return r

    def header(self, resume: Resume) -> None:
        p = self.para(align=WD_ALIGN_PARAGRAPH.CENTER)
        self.run(p, resume.name, 22, INK, bold=True)
        if resume.headline:
            self.run(self.para(before=1, align=WD_ALIGN_PARAGRAPH.CENTER), resume.headline, 10.5, ACCENT)
        if resume.contact:
            p = self.para(before=2, after=2, align=WD_ALIGN_PARAGRAPH.CENTER)
            for i, item in enumerate(c for c in resume.contact if c.text.strip()):
                if i:
                    self.run(p, "   •   ", 9, RULE)
                url = contact_url(item)
                if url:
                    _add_hyperlink(p, clean(item.text), url, 9 * self.s)
                else:
                    self.run(p, item.text, 9, MUTED)

    def section(self, title: str) -> None:
        p = self.para(before=9, after=3)
        p.paragraph_format.keep_with_next = True
        r = self.run(p, title.upper(), 10.5, ACCENT, bold=True)
        spacing = OxmlElement("w:spacing")  # letter-spacing, like the PDF heading
        spacing.set(qn("w:val"), "18")
        r._element.get_or_add_rPr().append(spacing)
        border = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        for k, v in {"w:val": "single", "w:sz": "6", "w:space": "1", "w:color": "%02X%02X%02X" % RULE}.items():
            bottom.set(qn(k), v)
        border.append(bottom)
        p._p.get_or_add_pPr().append(border)

    def entry(self, parts, right: str) -> None:
        p = self.para(before=4, after=1)
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.tab_stops.add_tab_stop(self.text_width, WD_TAB_ALIGNMENT.RIGHT)
        for text, style, color, link in parts:
            if not text:
                continue
            if link:
                _add_hyperlink(p, clean(text), link, 10.3 * self.s, color=color, bold="B" in style)
            else:
                self.run(p, text, 10.3 if "B" in style else 9.7, color, bold="B" in style, italic="I" in style)
        if right:
            self.run(p, "\t" + right, 9, MUTED, italic=True)

    def paragraph(self, text: str, size: float = 9.8, color=BODY) -> None:
        self.run(self.para(after=1), text, size, color)

    def labelled(self, label: str, text: str) -> None:
        p = self.para(after=1.5)
        if label:
            self.run(p, f"{label}: ", 9.8, INK, bold=True)
        self.run(p, text, 9.8, BODY)

    def bullet(self, text: str) -> None:
        p = self.doc.add_paragraph(style="List Bullet")
        fmt = p.paragraph_format
        fmt.space_before, fmt.space_after, fmt.line_spacing = self.pt(0.5), self.pt(0.5), 1.08
        self.run(p, text, 9.8, BODY)


def to_docx(resume: Resume, page_target: str = "auto") -> bytes:
    # Use the same scale the PDF needed to hit the page target, so both files look alike.
    scale = to_pdf(resume, page_target).scale
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Mm(210), Mm(297)
    section.left_margin = section.right_margin = Mm(12 + 4 * scale)
    section.top_margin = section.bottom_margin = Mm(10 + 4 * scale)
    normal = doc.styles["Normal"]
    normal.font.name, normal.font.size = "Calibri", Pt(9.8 * scale)

    w = _DocxWriter(doc, scale)
    w.header(resume)
    if resume.summary:
        w.section("Summary")
        w.paragraph(resume.summary)
    if resume.skills:
        w.section("Skills")
        for g in resume.skills:
            w.labelled(g.category, ", ".join(g.skills))
    if resume.experience:
        w.section("Experience")
        for job in resume.experience:
            w.entry(
                [(job.title, "B", INK, ""), (f"  ·  {job.company}" if job.company else "", "", BODY, "")],
                "  |  ".join(p for p in (job.location, job.dates) if p),
            )
            for b in job.bullets:
                w.bullet(b)
    if resume.projects:
        w.section("Projects")
        for proj in resume.projects:
            w.entry(
                [
                    (proj.name, "B", ACCENT if proj.url else INK, proj.url),
                    (f"  ·  {proj.details}" if proj.details else "", "I", MUTED, ""),
                ],
                "",
            )
            for b in proj.bullets:
                w.bullet(b)
    if resume.education:
        w.section("Education")
        for edu in resume.education:
            w.entry(
                [(edu.degree, "B", INK, ""), (f"  ·  {edu.institution}" if edu.institution else "", "", BODY, "")],
                edu.dates,
            )
            if edu.details:
                w.paragraph(edu.details, 9.4, MUTED)
    for extra in resume.extra_sections:
        if extra.items:
            w.section(extra.title)
            for item in extra.items:
                w.bullet(item)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
