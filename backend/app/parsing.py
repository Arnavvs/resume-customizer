"""Extract plain text from uploaded PDF and DOCX resumes."""

import io
import re
import zipfile

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


def file_extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def extract_text(filename: str, data: bytes) -> str:
    ext = file_extension(filename)
    if ext == "pdf":
        if not data.startswith(b"%PDF"):
            raise ResumeParseError("This file has a .pdf extension but isn't a valid PDF.")
        text = _pdf_text(data)
    elif ext == "docx":
        if not data.startswith(b"PK"):
            raise ResumeParseError("This file has a .docx extension but isn't a valid Word document.")
        text = _docx_text(data)
    else:
        raise ResumeParseError("Unsupported file type. Please upload a PDF or DOCX file.")

    text = normalize_text(text)
    if len(text) < MIN_TEXT_CHARS:
        raise ResumeParseError(
            "We couldn't read enough text from this file. If it's a scanned image or a PDF "
            "exported as pictures, please upload a text-based PDF or a DOCX instead."
        )
    return text


def _pdf_text(data: bytes) -> str:
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages) > MAX_PDF_PAGES:
                raise ResumeParseError(f"Resumes longer than {MAX_PDF_PAGES} pages aren't supported.")
            # A small x_tolerance keeps words in tightly-kerned resume templates from merging.
            pages = [page.extract_text(x_tolerance=1.5) or "" for page in pdf.pages]
    except ResumeParseError:
        raise
    except Exception as exc:  # pdfminer raises a zoo of exception types for corrupt files
        raise ResumeParseError("This PDF appears to be corrupted or password-protected.") from exc
    return "\n\n".join(pages)


def _docx_text(data: bytes) -> str:
    try:
        doc = Document(io.BytesIO(data))
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise ResumeParseError("This Word document appears to be corrupted.") from exc

    lines: list[str] = []
    for section in doc.sections:  # contact details often live in the header
        lines.extend(p.text for p in section.header.paragraphs)

    # Walk the body in document order so tables (common in resume templates) stay in place.
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            lines.append(Paragraph(child, doc).text)
        elif child.tag == qn("w:tbl"):
            lines.extend(_table_lines(Table(child, doc)))
    return "\n".join(lines)


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


_BULLET_CHARS = re.compile(r"^[ \t]*[▪●◦‣⁃∙·■•\-–*]+\s*", re.M)


def normalize_text(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace(" ", " ").replace("ﬁ", "fi").replace("ﬂ", "fl")
    text = _BULLET_CHARS.sub("• ", text)  # unify the many glyphs PDF templates use for bullets
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
