"""Unit tests for Phase 7 pipeline status — Tasks 1 & 2.

Tests:
 - Task 1: Document model Phase 7 additions (processing_status, error, failed_stage)
 - Task 1: INDEXES entry for document_processing_status_idx
 - Task 2: Status string constants in core.pipeline.status
 - Task 2: Celery app broker/backend config (D-03: no result backend)

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


# ---------------------------------------------------------------------------
# Task 2: Status string constants
# ---------------------------------------------------------------------------


def test_status_constants_values():
    """Status constants equal their expected literal values."""
    from core.pipeline.status import (
        STATUS_QUEUED,
        STATUS_PROCESSING,
        STATUS_WRITTEN,
        STATUS_FAILED,
    )
    assert STATUS_QUEUED == "queued"
    assert STATUS_PROCESSING == "processing"
    assert STATUS_WRITTEN == "written"
    assert STATUS_FAILED == "failed"


# ---------------------------------------------------------------------------
# Task 2: Celery app config (D-03 — no result backend)
# ---------------------------------------------------------------------------


def test_celery_broker_url_is_redis():
    """celery_app.conf.broker_url starts with redis:// (uses Settings.redis_url)."""
    from core.pipeline.celery_app import celery_app
    assert celery_app.conf.broker_url.startswith("redis://")


def test_celery_no_result_backend():
    """celery_app has no result backend (D-03: Neo4j is sole source of truth)."""
    from core.pipeline.celery_app import celery_app
    assert not celery_app.conf.result_backend
