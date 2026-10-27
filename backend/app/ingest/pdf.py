"""Resume PDF → text. pdfplumber first, pypdf as the fallback."""

import io
import logging
import re
from dataclasses import dataclass

log = logging.getLogger(__name__)
MIN_CHARS = 50


class PdfError(ValueError):
    pass


@dataclass
class PdfText:
    text: str
    extractor: str
    page_count: int


def _clean(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _pdfplumber(data: bytes) -> tuple[str, int]:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages = [p.extract_text(x_tolerance=1.5, y_tolerance=3) or "" for p in pdf.pages]
        return "\n\n".join(pages), len(pages)


def _pypdf(data: bytes) -> tuple[str, int]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = [p.extract_text() or "" for p in reader.pages]
    return "\n\n".join(pages), len(pages)


def extract_pdf_text(data: bytes) -> PdfText:
    if not data.startswith(b"%PDF"):
        raise PdfError("The file is not a PDF.")
    errors: list[str] = []
    for name, fn in (("pdfplumber", _pdfplumber), ("pypdf", _pypdf)):
        try:
            text, pages = fn(data)
        except Exception as e:  # each library raises its own error types on malformed PDFs
            log.warning("%s failed: %s", name, e)
            errors.append(f"{name}: {e}")
            continue
        text = _clean(text)
        if len(text) >= MIN_CHARS:
            return PdfText(text=text, extractor=name, page_count=pages)
        errors.append(f"{name}: only {len(text)} characters of text")
    raise PdfError(
        "Could not extract text from this PDF. If it is a scanned image, export it as a text PDF. "
        + "; ".join(errors)
    )
