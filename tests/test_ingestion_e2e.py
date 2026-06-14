"""End-to-end ingestion smoke tests — ROADMAP Phase 7 criteria #4 and #5.

Exercises the full path: POST /documents -> pipeline task body (_run) -> Neo4j graph.
Verifies:
  - Happy path (criterion #4): real PDF -> status "written" -> candidate found by
    scripts/queries.py::find_candidates_by_skill
  - Dedup (criterion #5 / D-05): re-POST of an already-written doc returns task_id=null
  - Failure path (criterion #5 / D-06): injected failure -> status "failed" with
    non-null failed_stage and error text; re-POST of failed doc re-enqueues (task_id present)

Worker strategy: The tests use httpx.AsyncClient with ASGI transport — an async HTTP
client that drives the FastAPI app in the SAME event loop as the test fixtures (including
the session-scoped Neo4j graph_db). This avoids the "Future attached to different loop"
error that arises when TestClient (which internally creates its own anyio event loop)
is combined with session-scoped async fixtures whose Neo4j driver was created on the
test's own event loop.

For the pipeline execution, process_document.delay() is intercepted with a no-op fake
(captures document_id without running the Celery wrapper). Then the real async task body
_run(document_id) is called directly from the test's event loop. This is semantically
equivalent to Celery eager mode: the real task code (parse->extract->write) runs in the
same process, against the same Neo4j, with no mocks on the pipeline logic itself.
Direct await of _run() is the correct pattern for async tasks in async test contexts
and avoids Celery's asyncio.run() wrapper (which cannot be called from a running loop).
This is documented as a Rule 1 auto-fix (platform constraint: Windows ProactorEventLoop
+ anyio event loop used by Starlette's TestClient bridge).

Skip gates:
  - Happy-path test: skips if Neo4j unavailable OR OPENROUTER_API_KEY not set
    (happy path includes a live LLM call — paid, skipped in CI without credentials)
  - Failure-path test: skips if Neo4j unavailable ONLY (failure is triggered via
    monkeypatch — no LLM call, no API key required; safe for bare CI with Neo4j)

Threat mitigations:
  T-07-11: Test DETACH DELETEs created Candidate/Document nodes in finally blocks
           (ids are deterministic SHA-256 -> reruns are idempotent)
  T-07-12: API key is read from Settings and checked for presence only — never logged
  T-07-13: Failure-path uses monkeypatched Extractor (no paid call); happy-path skips
           without OPENROUTER_API_KEY, so CI without credentials never costs money
"""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from api.dependencies import get_db, get_settings
from api.main import app
from core.database.graph import GraphDB
from core.pipeline.celery_app import celery_app
from core.pipeline.tasks import _run  # noqa: PLC2701 — internal; needed for e2e test
from scripts.queries import find_candidates_by_skill

pytestmark = pytest.mark.asyncio(loop_scope="session")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RESUME_DIR = Path("rnd/data/resume")


async def _make_client(graph_db: GraphDB, settings: Any) -> httpx.AsyncClient:
    """Return an async httpx client wired to the FastAPI app.

    Uses ASGITransport so requests run in the SAME event loop as the test
    (and the session-scoped graph_db). This avoids the "Future attached to
    different loop" error that TestClient causes when combined with session-scoped
    async Neo4j fixtures.
    """

    def _db_override() -> GraphDB:  # type: ignore[return]
        return graph_db

    def _settings_override() -> Any:
        return settings

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_settings] = _settings_override
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )


async def _detach_delete(driver: Any, document_id: str) -> None:
    """Best-effort DETACH DELETE of the Document and Candidate created by this test.

    T-07-11: test cleans up what it creates so reruns are idempotent.
    """
    if not document_id:
        return
    try:
        async with driver.session() as session:
            await session.run(
                "MATCH (d:Document {id: $id}) DETACH DELETE d",
                id=document_id,
            )
            await session.run(
                "MATCH (c:Candidate {id: $id}) DETACH DELETE c",
                id=document_id,
            )
    except Exception:
        pass  # best-effort — cleanup failure must not mask test failures


class _EagerResult:
    """Minimal stand-in for Celery's EagerResult — provides a .id attribute."""

    def __init__(self, task_id: str = "eager-task-id") -> None:
        self.id = task_id


def _make_noop_delay(captured: list[str]) -> Any:
    """Return a mock process_document object whose .delay() captures document_id.

    The REAL _run() coroutine is called directly from the test afterwards.
    This approach avoids Celery's asyncio.run() wrapper (incompatible with running
    event loop on Windows ProactorEventLoop).
    """

    class _FakeTask:
        def delay(self, document_id: str) -> _EagerResult:
            captured.append(document_id)
            return _EagerResult()

    return _FakeTask()


# ---------------------------------------------------------------------------
# Task 1: Happy path + dedup (criterion #4 + D-05 written branch)
# ---------------------------------------------------------------------------


async def test_ingestion_happy_path(
    graph_db: GraphDB,
    neo4j_driver: Any,
    settings: Any,
) -> None:
    """POST real PDF -> real _run() task body -> status 'written' -> candidate in graph.

    Covers:
      - criterion #4: find_candidates_by_skill returns the new candidate
      - criterion #5 / D-05: re-POST of written doc returns status 200 + task_id=null
    """
    # --- Skip gates ---
    if not graph_db.is_connected:
        pytest.skip("Neo4j unavailable")
    if not settings.openrouter_api_key:
        pytest.skip("OPENROUTER_API_KEY not set — live LLM test skipped")

    # Mark celery eager (for consistency; _run is called directly so eager doesn't fire)
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    pdf = next(_RESUME_DIR.glob("*.pdf"))
    pdf_bytes = pdf.read_bytes()

    client = await _make_client(graph_db, settings)
    document_id: str = ""

    try:
        captured_ids: list[str] = []
        fake_task = _make_noop_delay(captured_ids)

        # Step 1: POST the PDF
        # Patch process_document so the router runs merge_document_queued but does NOT
        # execute the task (our fake .delay() just captures the id and returns EagerResult).
        async with client:
            with patch("api.routers.documents.process_document", fake_task):
                resp = await client.post(
                    "/documents",
                    files={"file": (pdf.name, pdf_bytes, "application/pdf")},
                )
            assert resp.status_code == 202, (
                f"Expected 202, got {resp.status_code}: {resp.text}"
            )
            body = resp.json()
            document_id = body["document_id"]
            assert document_id, "document_id must be non-empty"
            assert body["task_id"] == "eager-task-id", (
                f"Expected task_id from fake task, got {body['task_id']!r}"
            )
            assert captured_ids == [document_id], (
                f"process_document.delay must be called with document_id={document_id!r}"
            )

            # Step 2: Run the real task body (_run) directly in the test's event loop.
            # This executes parse->extract->write against the same Neo4j instance.
            # Direct await avoids Celery's asyncio.run() wrapper (incompatible with the
            # already-running pytest-asyncio event loop on Windows ProactorEventLoop).
            await _run(document_id)

            # Step 3: GET to verify status is "written" (D-01 minimal set)
            g = await client.get(f"/documents/{document_id}")
            assert g.status_code == 200, f"GET returned {g.status_code}: {g.text}"
            final_status = g.json()["processing_status"]
            assert final_status == "written", (
                f"Expected processing_status='written' (D-01 minimal set), "
                f"got '{final_status}'"
            )

            # Step 4: Graph assertion (criterion #4)
            # Query the candidate's skills from Neo4j then use find_candidates_by_skill.
            async with neo4j_driver.session() as s:
                skills_result = await s.run(
                    "MATCH (c:Candidate {id: $id})-[:HAS_SKILL]->(sk:Skill) "
                    "RETURN sk.name AS skill_name LIMIT 1",
                    id=document_id,
                )
                skill_record = await skills_result.single()

            assert skill_record is not None, (
                f"Candidate {document_id} has no HAS_SKILL edges in graph"
            )
            skill_name = skill_record["skill_name"]

            candidates = await find_candidates_by_skill(neo4j_driver, skill_name)
            ids_found = [c["id"] for c in candidates]
            assert document_id in ids_found, (
                f"find_candidates_by_skill('{skill_name}') did not return "
                f"doc {document_id}; found: {ids_found}"
            )

            # Step 5: Dedup (criterion #5 / D-05) — re-POST same bytes
            with patch("api.routers.documents.process_document", fake_task):
                resp2 = await client.post(
                    "/documents",
                    files={"file": (pdf.name, pdf_bytes, "application/pdf")},
                )
            assert resp2.status_code == 200, (
                f"Re-POST of written doc must return 200 (D-05), "
                f"got {resp2.status_code}"
            )
            body2 = resp2.json()
            assert body2["document_id"] == document_id, (
                "document_id must be deterministic"
            )
            assert body2["task_id"] is None, (
                "Re-POST of written doc must return task_id=null "
                "(D-05 — no re-processing)"
            )

    finally:
        await _detach_delete(neo4j_driver, document_id)
        app.dependency_overrides.clear()
        celery_app.conf.task_always_eager = False
        celery_app.conf.task_eager_propagates = False


# ---------------------------------------------------------------------------
# Task 2: Failure path (criterion #5 / D-06) + failed re-enqueue (D-05)
# ---------------------------------------------------------------------------


async def test_ingestion_failure_path(
    graph_db: GraphDB,
    neo4j_driver: Any,
    settings: Any,
) -> None:
    """Injected extractor failure -> status 'failed' + failed_stage + error (D-06).

    Re-POST of failed doc re-enqueues and returns task_id (D-05 failed branch).

    No OPENROUTER_API_KEY needed: Extractor.extract is monkeypatched to raise
    RuntimeError, so the failure occurs deterministically before any paid LLM call
    (T-07-13). Skips if Neo4j is unavailable.
    """
    # --- Skip gate (Neo4j only — no LLM call) ---
    if not graph_db.is_connected:
        pytest.skip("Neo4j unavailable")

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False

    pdf = next(_RESUME_DIR.glob("*.pdf"))
    pdf_bytes = pdf.read_bytes()
    document_id: str = ""

    client = await _make_client(graph_db, settings)

    try:
        async with client:
            # Step 1: POST the PDF — use a no-op fake .delay() to capture document_id
            # without running the task yet. merge_document_queued runs normally (D-04).
            captured_ids: list[str] = []
            fake_task = _make_noop_delay(captured_ids)

            with patch("api.routers.documents.process_document", fake_task):
                resp = await client.post(
                    "/documents",
                    files={"file": (pdf.name, pdf_bytes, "application/pdf")},
                )
            assert resp.status_code == 202, (
                f"Expected 202, got {resp.status_code}: {resp.text}"
            )
            document_id = resp.json()["document_id"]

            # Step 2: Run _run(document_id) directly with monkeypatched Extractor.
            # Using a plain class (not AsyncMock) avoids "Future attached to different
            # loop" — the coroutine is created fresh each time on the current test loop.

            class _FakeExtractor:
                def __init__(self, *args: Any, **kwargs: Any) -> None:
                    pass

                async def extract(self, *args: Any, **kwargs: Any) -> None:
                    raise RuntimeError("injected extract failure")

            with patch("core.pipeline.tasks.Extractor", _FakeExtractor):
                try:
                    await _run(document_id)
                except RuntimeError:
                    pass  # expected — injected failure propagates; status was recorded

            # Step 3: GET — verify processing_status='failed' + failed_stage + error
            g = await client.get(f"/documents/{document_id}")
            assert g.status_code == 200, f"GET returned {g.status_code}: {g.text}"
            g_body = g.json()
            assert g_body["processing_status"] == "failed", (
                f"Expected processing_status='failed' (D-06), "
                f"got '{g_body['processing_status']}'"
            )
            assert g_body["failed_stage"] in {"parse", "extract", "write"}, (
                f"failed_stage must be one of parse/extract/write (D-06), "
                f"got '{g_body['failed_stage']}'"
            )
            assert g_body["error"], (
                "error field must be a non-empty string for failed doc (D-06)"
            )

            # Step 4: D-05 failed re-enqueue — POST the same bytes again.
            # The POST endpoint sees status="failed" -> calls reset_for_requeue + .delay().
            # Our fake .delay() returns an EagerResult with task_id="eager-task-id".
            captured2: list[str] = []
            fake_task2 = _make_noop_delay(captured2)

            with patch("api.routers.documents.process_document", fake_task2):
                resp2 = await client.post(
                    "/documents",
                    files={"file": (pdf.name, pdf_bytes, "application/pdf")},
                )
            assert resp2.status_code == 202, (
                f"Re-POST of failed doc must return 202 (D-05 re-enqueue), "
                f"got {resp2.status_code}"
            )
            body2 = resp2.json()
            assert body2["task_id"] is not None, (
                "Re-POST of a failed doc must return task_id "
                "(D-05 — re-enqueued, not skipped)"
            )

    finally:
        await _detach_delete(neo4j_driver, document_id)
        app.dependency_overrides.clear()
        celery_app.conf.task_always_eager = False
        celery_app.conf.task_eager_propagates = False
