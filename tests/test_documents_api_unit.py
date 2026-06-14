"""Unit tests for POST /documents and GET /documents/{id} API endpoints.

Uses fastapi.testclient.TestClient with:
  - app.dependency_overrides[get_db] -> FakeGraphDB (is_connected=True)
  - app.dependency_overrides[get_settings] -> FakeSettings
  - monkeypatched process_document and status helpers
  - NO live Celery, Neo4j, or file I/O (storage patched to tmp_path)

Covers:
  - POST /documents: happy path, size cap (413), non-PDF (415), empty body (400), db down (503)
  - POST dedup (D-05): written->200/no-delay, queued->202/no-delay,
                        failed->202/delay+reset_for_requeue, brand-new->202/delay
  - GET /documents/{id}: found (200 + all D-06 fields), missing (404), db down (503)
"""

import hashlib
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.dependencies import get_db, get_settings


# ---------------------------------------------------------------------------
# Fake dependencies
# ---------------------------------------------------------------------------


class FakeSession:
    """Async context manager returning a mock neo4j AsyncSession."""

    def __init__(self, status_row: dict[str, Any] | None = None) -> None:
        self._status_row = status_row
        self.run = AsyncMock()

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *_: object) -> None:
        pass


class FakeGraphDB:
    """Minimal GraphDB stand-in used in dependency overrides."""

    def __init__(
        self,
        is_connected: bool = True,
        status_row: dict[str, Any] | None = None,
    ) -> None:
        self.is_connected = is_connected
        self._status_row = status_row
        self._session_run_calls: list[tuple[str, dict[str, Any]]] = []

    def session(self) -> "FakeSession":  # type: ignore[override]
        return FakeSession(status_row=self._status_row)


class FakeSettings:
    neo4j_uri = "bolt://localhost:7687"
    neo4j_user = "neo4j"
    neo4j_password = "test"
    storage_root = Path("/tmp/test_storage")


# ---------------------------------------------------------------------------
# Task result stub for Celery delay()
# ---------------------------------------------------------------------------


class FakeTaskResult:
    id = "task-123"


class FakeTask:
    def delay(self, *args: Any, **kwargs: Any) -> FakeTaskResult:
        return FakeTaskResult()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MINIMAL_PDF = b"%PDF-1.0\n1 0 obj<</Type /Catalog>>endobj\nxref\n0 1\n0000000000 65535 f \ntrailer<</Size 1/Root 1 0 R>>\nstartxref\n9\n%%EOF"
PDF_SHA256 = hashlib.sha256(MINIMAL_PDF).hexdigest()

LARGE_BYTES = b"x" * (10 * 1024 * 1024 + 1)  # 1 byte over 10 MiB


def make_client(
    is_connected: bool = True,
    status_row: dict[str, Any] | None = None,
) -> TestClient:
    """Build a TestClient with the given FakeGraphDB."""
    fake_db = FakeGraphDB(is_connected=is_connected, status_row=status_row)

    def override_db() -> FakeGraphDB:  # type: ignore[return]
        return fake_db

    def override_settings() -> FakeSettings:  # type: ignore[return]
        return FakeSettings()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = override_settings
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# POST /documents — brand-new upload (happy path)
# ---------------------------------------------------------------------------


def test_post_new_document_returns_202_with_ids(tmp_path: Path) -> None:
    """Brand-new PDF upload returns 202 with correct document_id and task_id."""
    FakeSettings.storage_root = tmp_path

    client = make_client()
    fake_task = FakeTask()

    with (
        patch("api.routers.documents.process_document", fake_task),
        patch("api.routers.documents.merge_document_queued", new_callable=AsyncMock) as mock_merge,
        patch("api.routers.documents._read_status", new_callable=AsyncMock, return_value=None),
    ):
        response = client.post(
            "/documents",
            files={"file": ("resume.pdf", MINIMAL_PDF, "application/pdf")},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["document_id"] == PDF_SHA256
    assert body["task_id"] == "task-123"
    mock_merge.assert_awaited_once()
    app.dependency_overrides.clear()


def test_post_document_merge_called_before_delay(tmp_path: Path) -> None:
    """D-04: merge_document_queued must be called BEFORE process_document.delay."""
    FakeSettings.storage_root = tmp_path
    call_order: list[str] = []

    async def fake_merge(*args: Any, **kwargs: Any) -> None:
        call_order.append("merge")

    class OrderedFakeTask:
        def delay(self, *args: Any, **kwargs: Any) -> FakeTaskResult:
            call_order.append("delay")
            return FakeTaskResult()

    client = make_client()

    with (
        patch("api.routers.documents.process_document", OrderedFakeTask()),
        patch("api.routers.documents.merge_document_queued", side_effect=fake_merge),
        patch("api.routers.documents._read_status", new_callable=AsyncMock, return_value=None),
    ):
        response = client.post(
            "/documents",
            files={"file": ("resume.pdf", MINIMAL_PDF, "application/pdf")},
        )

    assert response.status_code == 202
    assert call_order == ["merge", "delay"], f"Expected merge before delay, got: {call_order}"
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /documents — validation errors
# ---------------------------------------------------------------------------


def test_post_non_pdf_filename_returns_415(tmp_path: Path) -> None:
    """Non-.pdf extension -> 415 Unsupported Media Type."""
    FakeSettings.storage_root = tmp_path
    client = make_client()

    with patch("api.routers.documents.process_document", FakeTask()):
        response = client.post(
            "/documents",
            files={"file": ("resume.txt", b"plain text", "text/plain")},
        )

    assert response.status_code == 415
    app.dependency_overrides.clear()


def test_post_oversized_file_returns_413(tmp_path: Path) -> None:
    """Files > 10 MiB -> 413 Request Entity Too Large."""
    FakeSettings.storage_root = tmp_path
    client = make_client()

    with patch("api.routers.documents.process_document", FakeTask()):
        response = client.post(
            "/documents",
            files={"file": ("big.pdf", LARGE_BYTES, "application/pdf")},
        )

    assert response.status_code == 413
    app.dependency_overrides.clear()


def test_post_empty_file_returns_400(tmp_path: Path) -> None:
    """Empty PDF body -> 400 Bad Request."""
    FakeSettings.storage_root = tmp_path
    client = make_client()

    with patch("api.routers.documents.process_document", FakeTask()):
        response = client.post(
            "/documents",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )

    assert response.status_code == 400
    app.dependency_overrides.clear()


def test_post_neo4j_down_returns_503() -> None:
    """If db.is_connected is False -> 503 Service Unavailable."""
    client = make_client(is_connected=False)

    with patch("api.routers.documents.process_document", FakeTask()):
        response = client.post(
            "/documents",
            files={"file": ("resume.pdf", MINIMAL_PDF, "application/pdf")},
        )

    assert response.status_code == 503
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /documents — D-05 deduplication branches
# ---------------------------------------------------------------------------


def test_post_dedup_written_returns_200_no_delay(tmp_path: Path) -> None:
    """D-05: existing status=written -> 200 {task_id: null}, process_document.delay NOT called."""
    FakeSettings.storage_root = tmp_path
    client = make_client()
    mock_task = MagicMock()
    mock_task.delay = MagicMock(return_value=FakeTaskResult())

    existing = {
        "processing_status": "written",
        "error": None,
        "failed_stage": None,
    }

    with (
        patch("api.routers.documents.process_document", mock_task),
        patch("api.routers.documents._read_status", new_callable=AsyncMock, return_value=existing),
        patch("api.routers.documents.merge_document_queued", new_callable=AsyncMock),
    ):
        response = client.post(
            "/documents",
            files={"file": ("resume.pdf", MINIMAL_PDF, "application/pdf")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == PDF_SHA256
    assert body["task_id"] is None
    mock_task.delay.assert_not_called()
    app.dependency_overrides.clear()


def test_post_dedup_queued_returns_202_no_delay(tmp_path: Path) -> None:
    """D-05: existing status=queued -> 202 {task_id: null}, delay NOT called."""
    FakeSettings.storage_root = tmp_path
    client = make_client()
    mock_task = MagicMock()
    mock_task.delay = MagicMock(return_value=FakeTaskResult())

    existing = {
        "processing_status": "queued",
        "error": None,
        "failed_stage": None,
    }

    with (
        patch("api.routers.documents.process_document", mock_task),
        patch("api.routers.documents._read_status", new_callable=AsyncMock, return_value=existing),
        patch("api.routers.documents.merge_document_queued", new_callable=AsyncMock),
    ):
        response = client.post(
            "/documents",
            files={"file": ("resume.pdf", MINIMAL_PDF, "application/pdf")},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["task_id"] is None
    mock_task.delay.assert_not_called()
    app.dependency_overrides.clear()


def test_post_dedup_processing_returns_202_no_delay(tmp_path: Path) -> None:
    """D-05: existing status=processing -> 202 {task_id: null}, delay NOT called."""
    FakeSettings.storage_root = tmp_path
    client = make_client()
    mock_task = MagicMock()
    mock_task.delay = MagicMock(return_value=FakeTaskResult())

    existing = {
        "processing_status": "processing",
        "error": None,
        "failed_stage": None,
    }

    with (
        patch("api.routers.documents.process_document", mock_task),
        patch("api.routers.documents._read_status", new_callable=AsyncMock, return_value=existing),
        patch("api.routers.documents.merge_document_queued", new_callable=AsyncMock),
    ):
        response = client.post(
            "/documents",
            files={"file": ("resume.pdf", MINIMAL_PDF, "application/pdf")},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["task_id"] is None
    mock_task.delay.assert_not_called()
    app.dependency_overrides.clear()


def test_post_dedup_failed_returns_202_delay_called_and_resets(tmp_path: Path) -> None:
    """D-05/D-06: status=failed -> 202, delay IS called, reset_for_requeue is called."""
    FakeSettings.storage_root = tmp_path
    client = make_client()
    mock_task = MagicMock()
    mock_task.delay = MagicMock(return_value=FakeTaskResult())

    existing = {
        "processing_status": "failed",
        "error": "parse error",
        "failed_stage": "parse",
    }

    with (
        patch("api.routers.documents.process_document", mock_task),
        patch("api.routers.documents._read_status", new_callable=AsyncMock, return_value=existing),
        patch(
            "api.routers.documents.reset_for_requeue", new_callable=AsyncMock
        ) as mock_reset,
        patch("api.routers.documents.merge_document_queued", new_callable=AsyncMock),
    ):
        response = client.post(
            "/documents",
            files={"file": ("resume.pdf", MINIMAL_PDF, "application/pdf")},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["document_id"] == PDF_SHA256
    assert body["task_id"] == "task-123"
    mock_task.delay.assert_called_once_with(PDF_SHA256)
    mock_reset.assert_awaited_once()
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /documents/{document_id}
# ---------------------------------------------------------------------------


def _mock_read_status_for_get(
    status_row: dict[str, Any] | None,
) -> Any:
    """Return a patched _read_status that yields status_row."""
    return patch(
        "api.routers.documents._read_status",
        new_callable=AsyncMock,
        return_value=status_row,
    )


def test_get_document_found_returns_200_with_all_fields() -> None:
    """GET /documents/{id} for existing node -> 200 with document_id + all D-06 fields."""
    client = make_client()
    row = {
        "processing_status": "written",
        "error": None,
        "failed_stage": None,
    }

    with _mock_read_status_for_get(row):
        response = client.get(f"/documents/{PDF_SHA256}")

    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == PDF_SHA256
    assert body["processing_status"] == "written"
    assert "error" in body
    assert "failed_stage" in body
    app.dependency_overrides.clear()


def test_get_document_with_failure_fields() -> None:
    """GET returns error and failed_stage for a failed document (D-06)."""
    client = make_client()
    row = {
        "processing_status": "failed",
        "error": "parse error message",
        "failed_stage": "parse",
    }

    with _mock_read_status_for_get(row):
        response = client.get(f"/documents/{PDF_SHA256}")

    assert response.status_code == 200
    body = response.json()
    assert body["processing_status"] == "failed"
    assert body["error"] == "parse error message"
    assert body["failed_stage"] == "parse"
    app.dependency_overrides.clear()


def test_get_document_missing_returns_404() -> None:
    """GET /documents/{id} for a non-existent document -> 404."""
    client = make_client()

    with _mock_read_status_for_get(None):
        response = client.get(f"/documents/{PDF_SHA256}")

    assert response.status_code == 404
    app.dependency_overrides.clear()


def test_get_document_neo4j_down_returns_503() -> None:
    """GET /documents/{id} when db is down -> 503."""
    client = make_client(is_connected=False)

    with _mock_read_status_for_get(None):
        response = client.get(f"/documents/{PDF_SHA256}")

    assert response.status_code == 503
    app.dependency_overrides.clear()
