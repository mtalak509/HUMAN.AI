"""Extraction backend seam for PDF text extraction.

Defines the TextExtractorBackend Protocol (D-02) so that alternative backends
(pdfplumber, OCR) can drop in without changing PdfParser.

Current concrete implementation: PyPdfBackend (D-01 — pypdf only for v1).
pdfplumber and OCR backends are deferred (D-01 / Phase 4 scope narrowing D-03).
"""

from pathlib import Path
from typing import Protocol, runtime_checkable

from loguru import logger


@runtime_checkable
class TextExtractorBackend(Protocol):
    """Structural subtyping seam for PDF text extraction (D-02).

    Any object with `extract(pdf_path: Path) -> tuple[str, str]` satisfies
    this protocol — no inheritance required.

    Returns:
        (extracted_text, extraction_status) where:
            extracted_text: full text with --- PAGE i --- markers
            extraction_status: "ok" | "empty"

    Contract:
        MUST NOT raise on image-only PDF — returns ("", "empty").
    """

    def extract(self, pdf_path: Path) -> tuple[str, str]: ...


class PyPdfBackend:
    """pypdf-only extraction backend (D-01).

    Ported from rnd/src/pdf_parser.py:
    - Inserts ``--- PAGE {i} ---`` markers (D-05)
    - Guards against None/empty page text (Pitfall 1: pypdf returns "" not None; keep `or ""`)
    - Logs empty pages at WARNING level with positional {} placeholders (CLAUDE.md)
    - Returns ("", "empty") for all-blank PDFs instead of raising (D-08)
    """

    PARSER_VERSION: str = "pypdf-v1"

    def extract(self, pdf_path: Path) -> tuple[str, str]:
        """Extract text from a PDF file.

        Args:
            pdf_path: Absolute or relative path to a .pdf file.

        Returns:
            (text, status) where status is "ok" | "empty".
        """
        # Local import keeps module-level import fast; pypdf is only loaded on first extraction
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        pages: list[str] = []
        empty_pages: list[int] = []

        for i, page in enumerate(reader.pages, start=1):
            # Pitfall 1: extract_text() returns "" (not None) for image-only pages in pypdf 4+;
            # keep the `or ""` guard for safety across pypdf versions.
            page_text = (page.extract_text() or "").strip()
            if not page_text:
                empty_pages.append(i)
            # D-05: exact marker style "--- PAGE {i} ---" (consumers parse this format)
            pages.append(f"--- PAGE {i} ---\n{page_text}")

        if empty_pages:
            logger.warning(
                "pdf_parser: empty pages file={} pages={}",
                pdf_path.name,
                empty_pages,
            )

        text = "\n\n".join(pages)
        status = "empty" if not text.strip() else "ok"  # D-08

        logger.info(
            "pdf_parser: extracted file={} pages={} chars={} status={}",
            pdf_path.name,
            len(pages),
            len(text),
            status,
        )

        return text, status
