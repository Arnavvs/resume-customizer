"""Extract plain text and hyperlinks from uploaded PDF and DOCX resumes."""

import io
import re
import zipfile
from dataclasses import dataclass, field

import pdfplumber
from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

SUPPORTED_EXTENSIONS = {"pdf", "docx"}
MIN_TEXT_CHARS = 100
MAX_PDF_PAGES = 10


class ResumeParseError(ValueError):
    """Raised when an uploaded file cannot be turned into usable resume text."""


@dataclass
class Link:
    text: str  # anchor text as shown in the document ("GitHub", "linkedin.com/in/jane", ...)
    url: str


@dataclass
class ExtractedResume:
    text: str
    links: list[Link] = field(default_factory=list)


def file_extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def extract(filename: str, data: bytes) -> ExtractedResume:
    """Text plus hyperlinks. Plain-text extraction drops link targets (a "GitHub" label pointing
    to github.com/jane loses its URL), so links are read separately from the file structure."""
    ext = file_extension(filename)
    if ext == "pdf":
        if not data.startswith(b"%PDF"):
            raise ResumeParseError("This file has a .pdf extension but isn't a valid PDF.")
        text, links = _pdf_extract(data)
    elif ext == "docx":
        if not data.startswith(b"PK"):
            raise ResumeParseError("This file has a .docx extension but isn't a valid Word document.")
        text, links = _docx_extract(data)
    else:
        raise ResumeParseError("Unsupported file type. Please upload a PDF or DOCX file.")

    text = normalize_text(text)
    if len(text) < MIN_TEXT_CHARS:
        raise ResumeParseError(
            "We couldn't read enough text from this file. If it's a scanned image or a PDF "
            "exported as pictures, please upload a text-based PDF or a DOCX instead."
        )
    return ExtractedResume(text=text, links=_dedupe(links))


def extract_text(filename: str, data: bytes) -> str:
    return extract(filename, data).text


def _dedupe(links: list[Link]) -> list[Link]:
    seen: dict[str, Link] = {}
    for link in links:
        url = link.url.strip()
        if url.lower().startswith(("http://", "https://", "mailto:", "tel:")):
            seen.setdefault(url, Link(text=" ".join(link.text.split()), url=url))
    return list(seen.values())


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def _pdf_extract(data: bytes) -> tuple[str, list[Link]]:
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages) > MAX_PDF_PAGES:
                raise ResumeParseError(f"Resumes longer than {MAX_PDF_PAGES} pages aren't supported.")
            # A small x_tolerance keeps words in tightly-kerned resume templates from merging.
            pages = [page.extract_text(x_tolerance=1.5) or "" for page in pdf.pages]
            links = [link for page in pdf.pages for link in _pdf_page_links(page)]
    except ResumeParseError:
        raise
    except Exception as exc:  # pdfminer raises a zoo of exception types for corrupt files
        raise ResumeParseError("This PDF appears to be corrupted or password-protected.") from exc
    return "\n\n".join(pages), links


def _pdf_page_links(page) -> list[Link]:
    links = []
    for h in page.hyperlinks:
        try:  # anchor text = whatever is printed inside the link rectangle
            bbox = (
                max(h["x0"] - 1, 0),
                max(h["top"] - 1, 0),
                min(h["x1"] + 1, page.width),
                min(h["bottom"] + 1, page.height),
            )
            text = page.crop(bbox).extract_text() or ""
        except Exception:
            text = ""
        links.append(Link(text=text, url=h.get("uri") or ""))
    return links


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------


def _docx_extract(data: bytes) -> tuple[str, list[Link]]:
    try:
        doc = Document(io.BytesIO(data))
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise ResumeParseError("This Word document appears to be corrupted.") from exc

    lines: list[str] = []
    links: list[Link] = []
    for section in doc.sections:  # contact details often live in the header
        lines.extend(p.text for p in section.header.paragraphs)
        links.extend(_docx_links(section.header.part, section.header._element))

    # Walk the body in document order so tables (common in resume templates) stay in place.
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            lines.append(Paragraph(child, doc).text)
        elif child.tag == qn("w:tbl"):
            lines.extend(_table_lines(Table(child, doc)))
    links.extend(_docx_links(doc.part, doc.element.body))
    return "\n".join(lines), links


def _docx_links(part, element) -> list[Link]:
    links = []
    for h in element.iter(qn("w:hyperlink")):
        rel_id = h.get(qn("r:id"))
        if not rel_id or rel_id not in part.rels:
            continue  # internal bookmark links have no external target
        text = "".join(t.text or "" for t in h.iter(qn("w:t")))
        links.append(Link(text=text, url=part.rels[rel_id].target_ref))
    return links


def _table_lines(table: Table) -> list[str]:
    lines: list[str] = []
    for row in table.rows:
        seen: set[int] = set()
        cells = []
        for cell in row.cells:
            if id(cell._tc) in seen:  # merged cells repeat the same underlying element
                continue
            seen.add(id(cell._tc))
            if cell.text.strip():
                cells.append(cell.text.strip())
        if cells:
            lines.append(" | ".join(cells))
    return lines


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

# The many glyphs PDF templates use for bullets (incl. Symbol-font private-use characters).
_BULLET_CHARS = re.compile(
    "^[ \t]*[▪●◦‣⁃∙·■•\\-–*]+\\s*", re.M
)


def normalize_text(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace(" ", " ").replace("ﬁ", "fi").replace("ﬂ", "fl")
    text = _BULLET_CHARS.sub("• ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
