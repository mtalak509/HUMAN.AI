"""Unit tests for Phase 7 pipeline status — Task 1: Document model extensions.

Tests the Document model's Phase 7 additions (processing_status, error, failed_stage)
and the new INDEXES entry for document_processing_status_idx.
No infra required — pure unit tests.
"""

import pytest

from core.schemas.models import Document
from core.database.migrations import INDEXES


# ---------------------------------------------------------------------------
# Document model validation — processing_status / error / failed_stage
# ---------------------------------------------------------------------------


def test_document_queued_state_validates():
    """Document with processing_status=queued and no error fields validates."""
    doc = Document(id="x", processing_status="queued", error=None, failed_stage=None)
    assert doc.processing_status == "queued"
    assert doc.error is None
    assert doc.failed_stage is None


def test_document_failed_state_validates():
    """Document with processing_status=failed + error/failed_stage validates."""
    doc = Document(
        id="x",
        processing_status="failed",
        error="boom",
        failed_stage="extract",
    )
    assert doc.processing_status == "failed"
    assert doc.error == "boom"
    assert doc.failed_stage == "extract"


def test_document_processing_status_defaults_none():
    """New Document(id=...) has processing_status=None by default."""
    doc = Document(id="doc-1")
    assert doc.processing_status is None


def test_document_written_state_validates():
    """Document with processing_status=written validates."""
    doc = Document(id="x", processing_status="written")
    assert doc.processing_status == "written"


def test_document_processing_state_validates():
    """Document with processing_status=processing validates."""
    doc = Document(id="x", processing_status="processing")
    assert doc.processing_status == "processing"


def test_document_existing_extraction_status_unaffected():
    """extraction_status (Phase 4 field) remains independent of Phase 7 fields."""
    doc = Document(id="x", extraction_status="ok", processing_status="written")
    assert doc.extraction_status == "ok"
    assert doc.processing_status == "written"


# ---------------------------------------------------------------------------
# Migrations INDEXES — document_processing_status_idx
# ---------------------------------------------------------------------------


def test_document_processing_status_idx_in_indexes():
    """INDEXES list contains document_processing_status_idx entry."""
    index_names = {name for name, _ in INDEXES}
    assert "document_processing_status_idx" in index_names


def test_document_processing_status_idx_cypher_correct():
    """The index Cypher targets Document.processing_status."""
    index_map = {name: cypher for name, cypher in INDEXES}
    cypher = index_map["document_processing_status_idx"]
    assert "Document" in cypher
    assert "processing_status" in cypher
    assert "IF NOT EXISTS" in cypher
