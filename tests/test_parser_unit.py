"""Unit tests for core.parser — PARSE-01, PARSE-02, SHA-256 idempotency.

These tests do NOT require Neo4j, Qdrant, or Redis.
All storage writes go to pytest's tmp_path.
"""

from pathlib import Path

import pytest

from core.parser import ParseResult, PdfParser
from core.parser._backend import PyPdfBackend, TextExtractorBackend

pytestmark = pytest.mark.asyncio(loop_scope="session")

# Pick any resume PDF from the R&D corpus — deterministic across runs
_RESUME_PDF = next(Path("rnd/data/resume").glob("*.pdf"))


# ---------------------------------------------------------------------------
# Backend unit tests (sync)
# ---------------------------------------------------------------------------


def test_pypdf_backend_extracts_text() -> None:
    """PyPdfBackend.extract() returns non-empty text and status 'ok' for a real resume."""
    backend = PyPdfBackend()
    text, status = backend.extract(_RESUME_PDF)
    assert status == "ok"
    assert len(text) > 100


def test_page_markers_format() -> None:
    """Extracted text contains '--- PAGE 1 ---' marker."""
    backend = PyPdfBackend()
    text, _ = backend.extract(_RESUME_PDF)
    assert "--- PAGE 1 ---" in text


def test_empty_pdf_graceful() -> None:
    """A PDF whose every page yields empty text returns ('', 'empty') without raising."""
    import io

    from pypdf import PdfWriter

    # Build a minimal 1-page blank PDF in memory
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    blank_bytes = buf.read()

    # Write to tmp file via a real path (PyPdfBackend expects a Path)
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(blank_bytes)
        tmp_path_str = f.name

    backend = PyPdfBackend()
    try:
        text, status = backend.extract(Path(tmp_path_str))
    finally:
        Path(tmp_path_str).unlink(missing_ok=True)

    assert text == ""
    assert status == "empty"


def test_extraction_status() -> None:
    """Extracting a valid resume PDF returns status == 'ok'."""
    backend = PyPdfBackend()
    _, status = backend.extract(_RESUME_PDF)
    assert status == "ok"


def test_backend_protocol_structural_subtyping() -> None:
    """PyPdfBackend satisfies TextExtractorBackend at runtime (runtime_checkable)."""
    assert isinstance(PyPdfBackend(), TextExtractorBackend)


# ---------------------------------------------------------------------------
# PdfParser async tests — use tmp_path for storage
# ---------------------------------------------------------------------------


async def test_storage_layout(tmp_path: Path) -> None:
    """After parse(), the original PDF exists at tmp_path/documents/{id}/<filename>."""
    parser = PdfParser(db=None, storage_root=tmp_path)
    result = await parser.parse(_RESUME_PDF)

    expected_pdf = tmp_path / "documents" / result.document_id / _RESUME_PDF.name
    assert expected_pdf.exists(), f"PDF not found at {expected_pdf}"


async def test_text_md_saved(tmp_path: Path) -> None:
    """After parse(), text.md exists and contains '--- PAGE'."""
    parser = PdfParser(db=None, storage_root=tmp_path)
    result = await parser.parse(_RESUME_PDF)

    text_md = tmp_path / "documents" / result.document_id / "text.md"
    assert text_md.exists(), f"text.md not found at {text_md}"
    content = text_md.read_text(encoding="utf-8")
    assert "--- PAGE" in content
    assert content == result.extracted_text


# ---------------------------------------------------------------------------
# SHA-256 idempotency
# ---------------------------------------------------------------------------


def test_sha256_idempotent() -> None:
    """Hashing the same PDF bytes twice produces the same document_id."""
    pdf_bytes = _RESUME_PDF.read_bytes()
    id1 = PdfParser._compute_document_id(pdf_bytes)
    id2 = PdfParser._compute_document_id(pdf_bytes)
    assert id1 == id2
    assert len(id1) == 64  # full SHA-256 hex


def test_sha256_is_64_chars() -> None:
    """document_id is exactly 64 hex characters (full SHA-256)."""
    pdf_bytes = _RESUME_PDF.read_bytes()
    doc_id = PdfParser._compute_document_id(pdf_bytes)
    assert len(doc_id) == 64
    assert all(c in "0123456789abcdef" for c in doc_id)
