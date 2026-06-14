"""Unit tests for core.pipeline.tasks.process_document — Task 3.

Tests use async mock doubles for PdfParser, Extractor, GraphWriter, and GraphDB.
No infra required — purely unit tests with monkeypatching.

Scenarios tested:
  1. Success path: set_status(processing) -> parse -> extract -> write -> set_status(written)
  2. Extract failure: set_failed(failed_stage="extract") and exception propagates
  3. Neo4j-down guard: RuntimeError raised before any status write (CONTEXT ⚠)

All tests use function-scoped asyncio loop (pytest.mark.asyncio default).
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from core.extractor.schema import ExtractedCandidate

# Note: async tests are decorated individually with @pytest.mark.asyncio
# to avoid warnings on sync helper tests at module level.


# ---------------------------------------------------------------------------
# Fake doubles
# ---------------------------------------------------------------------------


class FakeSession:
    """Records run() calls for assertion."""

    def __init__(self):
        self.calls: list[dict] = []

    async def run(self, cypher: str, **kwargs):
        self.calls.append({"cypher": cypher, **kwargs})


class FakeGraphDB:
    """Fake GraphDB exposing is_connected + async session() CM + close."""

    def __init__(self, connected: bool = True):
        self.is_connected = connected
        self.session_obj = FakeSession()

    async def connect_with_retry(self, retries=3, delays=None):
        pass  # already "connected" or not

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[FakeSession, None]:
        if not self.is_connected:
            raise RuntimeError("Neo4j is not connected - cannot create session")
        yield self.session_obj

    async def close(self):
        pass


def _make_fake_parse_result(document_id: str = "abc123"):
    """Minimal frozen ParseResult-like namespace."""
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class FakeParseResult:
        document_id: str
        extracted_text: str
        file_uri: str
        text_uri: str
        extraction_status: str
        parser_version: str

    return FakeParseResult(
        document_id=document_id,
        extracted_text="resume text",
        file_uri=f"documents/{document_id}/resume.pdf",
        text_uri=f"documents/{document_id}/text.md",
        extraction_status="ok",
        parser_version="pypdf-v1",
    )


def _make_fake_candidate(document_id: str = "abc123") -> ExtractedCandidate:
    """Minimal valid ExtractedCandidate for testing."""
    return ExtractedCandidate(
        full_name="Test Candidate",
        contacts=[],
        experiences=[],
        education=[],
        skills=[],
        document_id=document_id,
        model_version="test-model",
    )


# ---------------------------------------------------------------------------
# Fixtures for patch targets
# ---------------------------------------------------------------------------

DOCUMENT_ID = "a" * 64  # 64-char fake SHA-256 hex


@pytest.fixture
def fake_db():
    return FakeGraphDB(connected=True)


@pytest.fixture
def fake_db_disconnected():
    return FakeGraphDB(connected=False)


# ---------------------------------------------------------------------------
# Test: success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_document_success_path(fake_db, tmp_path, monkeypatch):
    """Success path: set_status(processing) -> parse -> extract -> write -> set_status(written)."""
    from core.pipeline import tasks as tasks_mod

    # Create a fake PDF file to satisfy the glob/file lookup in _run
    doc_dir = tmp_path / "documents" / DOCUMENT_ID
    doc_dir.mkdir(parents=True)
    pdf_file = doc_dir / "resume.pdf"
    pdf_file.write_bytes(b"%PDF fake")

    parse_result = _make_fake_parse_result(DOCUMENT_ID)
    candidate = _make_fake_candidate(DOCUMENT_ID)

    # Patch GraphDB constructor to return our fake_db
    monkeypatch.setattr(tasks_mod, "GraphDB", lambda **kwargs: fake_db)

    # Patch PdfParser
    mock_parser_cls = MagicMock()
    mock_parser_instance = MagicMock()
    mock_parser_instance.parse = AsyncMock(return_value=parse_result)
    mock_parser_cls.return_value = mock_parser_instance
    monkeypatch.setattr(tasks_mod, "PdfParser", mock_parser_cls)

    # Patch Extractor
    mock_extractor_cls = MagicMock()
    mock_extractor_instance = MagicMock()
    mock_extractor_instance.extract = AsyncMock(return_value=candidate)
    mock_extractor_cls.return_value = mock_extractor_instance
    monkeypatch.setattr(tasks_mod, "Extractor", mock_extractor_cls)

    # Patch GraphWriter
    mock_writer_cls = MagicMock()
    mock_writer_instance = MagicMock()
    mock_writer_instance.write = AsyncMock(return_value=None)
    mock_writer_cls.return_value = mock_writer_instance
    monkeypatch.setattr(tasks_mod, "GraphWriter", mock_writer_cls)

    # Patch get_settings to use tmp_path as storage_root
    from core.config import Settings
    fake_settings = MagicMock(spec=Settings)
    fake_settings.neo4j_uri = "bolt://localhost:7687"
    fake_settings.neo4j_user = "neo4j"
    fake_settings.neo4j_password = "test"
    fake_settings.storage_root = tmp_path
    monkeypatch.setattr(tasks_mod, "get_settings", lambda: fake_settings)

    # Track status calls via the session
    session_calls: list[str] = []
    original_run = fake_db.session_obj.run

    async def tracking_run(cypher: str, **kwargs):
        session_calls.append(kwargs.get("status", kwargs.get("failed", "?")))
        await original_run(cypher, **kwargs)

    fake_db.session_obj.run = tracking_run

    # Run the async orchestrator
    await tasks_mod._run(DOCUMENT_ID)

    # Assert parse, extract, write were each called once
    mock_parser_instance.parse.assert_called_once()
    mock_extractor_instance.extract.assert_called_once_with(
        parse_result.extracted_text, DOCUMENT_ID
    )
    mock_writer_instance.write.assert_called_once_with(candidate, DOCUMENT_ID)


@pytest.mark.asyncio
async def test_process_document_sets_processing_then_written(fake_db, tmp_path, monkeypatch):
    """Status transitions: processing -> written on success path."""
    from core.pipeline import tasks as tasks_mod
    from core.pipeline.status import STATUS_PROCESSING, STATUS_WRITTEN

    doc_dir = tmp_path / "documents" / DOCUMENT_ID
    doc_dir.mkdir(parents=True)
    (doc_dir / "resume.pdf").write_bytes(b"%PDF fake")

    parse_result = _make_fake_parse_result(DOCUMENT_ID)
    candidate = _make_fake_candidate(DOCUMENT_ID)

    monkeypatch.setattr(tasks_mod, "GraphDB", lambda **kwargs: fake_db)

    mock_parser_cls = MagicMock()
    mock_parser_cls.return_value.parse = AsyncMock(return_value=parse_result)
    monkeypatch.setattr(tasks_mod, "PdfParser", mock_parser_cls)

    mock_extractor_cls = MagicMock()
    mock_extractor_cls.return_value.extract = AsyncMock(return_value=candidate)
    monkeypatch.setattr(tasks_mod, "Extractor", mock_extractor_cls)

    mock_writer_cls = MagicMock()
    mock_writer_cls.return_value.write = AsyncMock(return_value=None)
    monkeypatch.setattr(tasks_mod, "GraphWriter", mock_writer_cls)

    from core.config import Settings
    fake_settings = MagicMock(spec=Settings)
    fake_settings.neo4j_uri = "bolt://localhost:7687"
    fake_settings.neo4j_user = "neo4j"
    fake_settings.neo4j_password = "test"
    fake_settings.storage_root = tmp_path
    monkeypatch.setattr(tasks_mod, "get_settings", lambda: fake_settings)

    # Track set_status calls
    status_sequence: list[str] = []

    async def spy_set_status(session, document_id, status):
        status_sequence.append(status)

    monkeypatch.setattr(tasks_mod, "set_status", spy_set_status)

    await tasks_mod._run(DOCUMENT_ID)

    assert STATUS_PROCESSING in status_sequence, "set_status(processing) not called"
    assert STATUS_WRITTEN in status_sequence, "set_status(written) not called"
    assert status_sequence.index(STATUS_PROCESSING) < status_sequence.index(STATUS_WRITTEN)


# ---------------------------------------------------------------------------
# Test: extract failure path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_document_extract_failure(fake_db, tmp_path, monkeypatch):
    """Extract exception -> set_failed(failed_stage='extract') and exception propagates."""
    from core.pipeline import tasks as tasks_mod

    doc_dir = tmp_path / "documents" / DOCUMENT_ID
    doc_dir.mkdir(parents=True)
    (doc_dir / "resume.pdf").write_bytes(b"%PDF fake")

    parse_result = _make_fake_parse_result(DOCUMENT_ID)

    monkeypatch.setattr(tasks_mod, "GraphDB", lambda **kwargs: fake_db)

    mock_parser_cls = MagicMock()
    mock_parser_cls.return_value.parse = AsyncMock(return_value=parse_result)
    monkeypatch.setattr(tasks_mod, "PdfParser", mock_parser_cls)

    extract_error = RuntimeError("LLM extraction failed")
    mock_extractor_cls = MagicMock()
    mock_extractor_cls.return_value.extract = AsyncMock(side_effect=extract_error)
    monkeypatch.setattr(tasks_mod, "Extractor", mock_extractor_cls)

    mock_writer_cls = MagicMock()
    monkeypatch.setattr(tasks_mod, "GraphWriter", mock_writer_cls)

    from core.config import Settings
    fake_settings = MagicMock(spec=Settings)
    fake_settings.neo4j_uri = "bolt://localhost:7687"
    fake_settings.neo4j_user = "neo4j"
    fake_settings.neo4j_password = "test"
    fake_settings.storage_root = tmp_path
    monkeypatch.setattr(tasks_mod, "get_settings", lambda: fake_settings)

    # Track set_failed calls
    failed_calls: list[dict] = []

    async def spy_set_failed(session, document_id, error, failed_stage):
        failed_calls.append({"error": error, "failed_stage": failed_stage})

    monkeypatch.setattr(tasks_mod, "set_failed", spy_set_failed)

    with pytest.raises(RuntimeError, match="LLM extraction failed"):
        await tasks_mod._run(DOCUMENT_ID)

    assert len(failed_calls) == 1, "set_failed should be called exactly once"
    assert failed_calls[0]["failed_stage"] == "extract"
    assert "LLM extraction failed" in failed_calls[0]["error"]

    # writer should NOT have been called
    mock_writer_cls.return_value.write.assert_not_called()


# ---------------------------------------------------------------------------
# Test: Neo4j-down guard (CONTEXT ⚠)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_document_neo4j_down_raises(fake_db_disconnected, tmp_path, monkeypatch):
    """When Neo4j is unavailable, _run raises RuntimeError — NO silent success."""
    from core.pipeline import tasks as tasks_mod

    monkeypatch.setattr(tasks_mod, "GraphDB", lambda **kwargs: fake_db_disconnected)

    mock_parser_cls = MagicMock()
    mock_parser_cls.return_value.parse = AsyncMock()
    monkeypatch.setattr(tasks_mod, "PdfParser", mock_parser_cls)

    mock_extractor_cls = MagicMock()
    monkeypatch.setattr(tasks_mod, "Extractor", mock_extractor_cls)

    mock_writer_cls = MagicMock()
    monkeypatch.setattr(tasks_mod, "GraphWriter", mock_writer_cls)

    from core.config import Settings
    fake_settings = MagicMock(spec=Settings)
    fake_settings.neo4j_uri = "bolt://localhost:7687"
    fake_settings.neo4j_user = "neo4j"
    fake_settings.neo4j_password = "test"
    fake_settings.storage_root = tmp_path
    monkeypatch.setattr(tasks_mod, "get_settings", lambda: fake_settings)

    with pytest.raises(RuntimeError, match="Neo4j unavailable"):
        await tasks_mod._run(DOCUMENT_ID)

    # parse/extract/write should never be called when Neo4j is down
    mock_parser_cls.return_value.parse.assert_not_called()


# ---------------------------------------------------------------------------
# Test: process_document task name (sync — no asyncio needed)
# ---------------------------------------------------------------------------


def test_process_document_task_name():
    """process_document Celery task has the correct name."""
    from core.pipeline.tasks import process_document
    assert process_document.name == "process_document"


# ---------------------------------------------------------------------------
# Test: no autoretry_for on process_document (D-07) (sync — no asyncio needed)
# ---------------------------------------------------------------------------


def test_process_document_no_autoretry():
    """process_document task has NO autoretry_for (fail-fast D-07)."""
    from core.pipeline.tasks import process_document
    # If autoretry_for is set, it appears on task.autoretry_for
    autoretry = getattr(process_document, "autoretry_for", ())
    assert not autoretry, f"Expected no autoretry_for but got: {autoretry}"
