---
phase: 07-ingestion-api
verified: 2026-06-14T20:00:00Z
status: human_needed
score: 5/5 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Run pytest tests/test_ingestion_e2e.py -v with Neo4j up and OPENROUTER_API_KEY set"
    expected: "test_ingestion_happy_path PASSED (real PDF -> status 'written' -> find_candidates_by_skill returns candidate); test_ingestion_failure_path PASSED (status 'failed' + failed_stage + error)"
    why_human: "Happy path requires a live LLM call (paid, ~2 min). Test infrastructure confirmed sound from SUMMARY self-check (2 passed in ~123s), but the verifier cannot execute live paid tests. This is the proof of ROADMAP criterion #4."
  - test: "Inspect CR-01 risk: simulate mid-pipeline Neo4j outage during parse/extract step (e.g. stop Neo4j after task.set_status(processing) but before parse completes)"
    expected: "Document should end up in 'failed' state (or at worst 'processing'), NOT 'written' with no data. With current code, db.session() will raise inside the except block, so the original exception is masked and the document is permanently stuck in 'processing'."
    why_human: "CR-01 (BLOCKER in review) cannot be exercised by automated grep/static analysis. The risk is a 'stuck in processing forever' state that blocks re-enqueue. The D-05 dedup logic treats processing as in-flight (returns 202/null without re-dispatch), so manual operator intervention (DETACH DELETE) would be required to recover. This is a production correctness gap, not tested by the unit or e2e suites."
---

# Phase 7: Ingestion API — Verification Report

**Phase Goal:** Полный ingestion-пайплайн доступен через HTTP API — POST /documents запускает Celery-задачу, GET /documents/{id} отдаёт статус; сквозной тест: PDF через API → кандидат в графе.

**Verified:** 2026-06-14T20:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | POST /documents (multipart, field `file`) returns {document_id, task_id} in < 200ms | VERIFIED | `api/routers/documents.py:92` `@router.post("/documents", status_code=202)` — SHA-256 computed from bytes, file saved, `merge_document_queued` called, `process_document.delay()` invoked, returns JSON with both fields. Registered in `api/main.py:59`. |
| 2 | GET /documents/{id} returns minimal D-01 status set: queued\|processing\|written\|failed; diagnostics via failed_stage | VERIFIED | `api/routers/documents.py:223` `@router.get("/documents/{document_id}")` — `_read_status()` queries `processing_status`, `error`, `failed_stage`; 404 on missing node; 503 when db disconnected. |
| 3 | Celery worker processes PDF: parse → extract → write without blocking HTTP server | VERIFIED | `core/pipeline/tasks.py:137` sync `process_document` task wraps `asyncio.run(_run(...))`. `_run()` calls `PdfParser.parse()` → `Extractor.extract()` → `GraphWriter.write()` in sequence. No result backend (D-03). `celery_app.py` configures redis broker only. |
| 4 | End-to-end test: POST real PDF → pipeline task body runs → find_candidates_by_skill finds candidate | VERIFIED (with noted deviation) | `tests/test_ingestion_e2e.py` exists and is substantive. POST is made via `httpx.AsyncClient`, `_run(document_id)` is called directly (bypassing `asyncio.run()` wrapper — documented Windows ProactorEventLoop constraint), `find_candidates_by_skill` is asserted. SUMMARY self-check: "2 passed in ~123s". See human verification item #1. |
| 5 | On error: status failed + error + failed_stage (D-06); repeat POST is status-smart (D-05: written→reuse, failed→re-run, in-flight→no-dup) | VERIFIED | `core/pipeline/tasks.py:97-126`: three `try/except` blocks call `set_failed(..., "parse"\|"extract"\|"write")` and re-raise. No `autoretry_for`. `api/routers/documents.py:153-193`: all four D-05 branches (written→200/null, queued\|processing→202/null, failed→`reset_for_requeue`+202/task_id, new→202/task_id). |

**Score:** 5/5 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `core/pipeline/status.py` | STATUS_* constants + merge_document_queued / set_status / set_failed / reset_for_requeue Cypher helpers | VERIFIED | All four functions present. All Cypher uses bound `$params` (T-07-01). `merge_document_queued` uses `ON CREATE SET` (D-05). `reset_for_requeue` sets `error=null, failed_stage=null` (D-06 freshness). |
| `core/pipeline/celery_app.py` | Celery app configured with redis_url broker, NO result backend | VERIFIED | `Celery("human_ai", broker=_settings.redis_url, include=["core.pipeline.tasks"])`. No `backend=` argument. grep confirms zero occurrences of `result_backend` in the file. |
| `core/pipeline/tasks.py` | process_document Celery task orchestrating parse→extract→write | VERIFIED | `@celery_app.task(name="process_document")` at line 137. `_run()` async orchestrator at line 43. `asyncio.run(_run(document_id))` at line 147. Neo4j-down guard at line 64. `is_connected=False` raises before any pipeline step (T-07-03). No `autoretry_for`. |
| `core/schemas/models.py` | Document model with processing_status, error, failed_stage | VERIFIED | Lines 93-95: `processing_status`, `error`, `failed_stage` all present as `str \| None = None` with D-01/D-06 comments. `extraction_status` (Phase 4) untouched. |
| `core/database/migrations.py` | Index on Document.processing_status | VERIFIED | Lines 99-100: `document_processing_status_idx` entry confirmed in INDEXES list. |
| `api/routers/documents.py` | POST /documents + GET /documents/{id} router | VERIFIED | Both routes implemented. `merge_document_queued` called before `process_document.delay`. `reset_for_requeue` used on failed branch. `MAX_UPLOAD_BYTES=10MiB`, `.pdf` suffix + content-type validation, `Path(filename).name` traversal guard. |
| `api/main.py` | Router registered via app.include_router | VERIFIED | Line 59: `app.include_router(documents.router)` after late import at line 57. |
| `api/dependencies.py` | get_db / get_settings DI helpers (circular-import safe) | VERIFIED | Canonical DI functions imported by router and tests. `api/main.py` also defines its own `get_db`/`get_settings` (WR-01 warning from review — divergent copies; `/health` uses `main.py` versions while router uses `api.dependencies` versions). |
| `tests/test_ingestion_e2e.py` | End-to-end ingestion smoke test | VERIFIED | 2 tests: `test_ingestion_happy_path` + `test_ingestion_failure_path`. `find_candidates_by_skill` called. Both skip cleanly without Neo4j. Happy path also skips without `OPENROUTER_API_KEY`. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `api/routers/documents.py` | `core/pipeline/tasks.py process_document` | `process_document.delay(document_id)` | WIRED | Line 208 (brand-new branch) and line 189 (failed branch). |
| `api/routers/documents.py` | `core/pipeline/status.py merge_document_queued` | Called inside `async with db.session()` block before `delay()` | WIRED | Line 205. D-04 ordering confirmed: session closes before `.delay()` is called (line 208 is outside the `async with` block). |
| `api/routers/documents.py` | `Document node processing_status` | `_read_status()` Cypher helper + GET response | WIRED | `_READ_STATUS_CYPHER` at lines 58-63; returned in GET response at line 252. |
| `core/pipeline/tasks.py` | `core/parser/pdf.py PdfParser.parse` | Direct async call inside `_run()` | WIRED | Line 91: `result = await parser.parse(pdf_path)`. |
| `core/pipeline/tasks.py` | `core/pipeline/status.py set_failed` | `except` block on each stage | WIRED | Three call sites: lines 99, 110, 124. Each opens its own session before calling `set_failed`. |
| `core/pipeline/celery_app.py` | `core/config.py Settings.redis_url` | `broker=_settings.redis_url` | WIRED | Line 21: `broker=_settings.redis_url`. |
| `tests/test_ingestion_e2e.py` | `api/routers/documents.py POST/GET` | `httpx.AsyncClient` with `ASGITransport` | WIRED | Lines 172-177, 197. HTTP calls made via async client. |
| `tests/test_ingestion_e2e.py` | `scripts/queries.py find_candidates_by_skill` | Post-written graph assertion | WIRED | Line 220: `await find_candidates_by_skill(neo4j_driver, skill_name)`. |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `api/routers/documents.py` GET | `processing_status`, `error`, `failed_stage` | `_READ_STATUS_CYPHER` → Neo4j MATCH | Yes — queries live Document node fields | FLOWING |
| `api/routers/documents.py` POST | `document_id` | `hashlib.sha256(data).hexdigest()` from actual uploaded bytes | Yes — derived from real bytes, not hardcoded | FLOWING |
| `core/pipeline/tasks.py _run()` | `pdf_path` | `pdf_dir.glob("*.pdf")[0]` | Yes — reads real filesystem; raises `FileNotFoundError` if absent | FLOWING (see WR-04 note) |

---

### Behavioral Spot-Checks

Step 7b: SKIPPED for live API/Celery (no running server). Unit tests serve as behavioral proxies.

Unit test evidence:
- `test_process_document_sets_processing_then_written` — asserts `STATUS_PROCESSING` in status sequence before `STATUS_WRITTEN` (PASS per SUMMARY)
- `test_process_document_extract_failure` — asserts `set_failed(failed_stage="extract")` and exception propagates (PASS per SUMMARY)
- `test_process_document_neo4j_down_raises` — asserts `RuntimeError("Neo4j unavailable")` before any pipeline call (PASS per SUMMARY)
- `test_documents_api_unit.py` — 14 tests covering all four POST D-05 branches and GET scenarios (PASS per SUMMARY)
- `test_ingestion_e2e.py` — 2 e2e tests (PASS per SUMMARY self-check; human confirmation required for live run)

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| API-01 | 07-02 | POST /documents принимает PDF, возвращает document_id и task_id | SATISFIED | `@router.post("/documents")` returns `{document_id, task_id}` |
| API-02 | 07-02 | GET /documents/{id} возвращает статус (D-01 minimal set) | SATISFIED | `@router.get("/documents/{document_id}")` returns `processing_status` + `error` + `failed_stage`; 404 when absent. Note: REQUIREMENTS.md lists "queued/parsing/extracting/writing/written/failed" but the roadmap explicitly documents D-02 deviation to minimal set queued\|processing\|written\|failed — this is the accepted contract. |
| PIPE-01 | 07-01, 07-03 | Полный цикл parse→extract→write выполняется асинхронно через Celery | SATISFIED | `process_document` Celery task orchestrates all three stages; e2e test drives real pipeline body |

No orphaned requirements detected: all three IDs (API-01, API-02, PIPE-01) appear in phase plans and are traced to implementation.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `core/pipeline/tasks.py` | 97-126 | `set_failed()` opens `db.session()` inside `except` block with no guard against a second Neo4j outage | WARNING | CR-01 from review: if Neo4j drops mid-pipeline, the session open itself raises, masking the original exception and leaving `processing_status='processing'` permanently. D-05 dedup then refuses re-enqueue (in-flight branch returns 202/null). Requires manual graph intervention to recover. |
| `api/main.py` | 62-67 | Duplicate `get_db`/`get_settings` definitions shadow canonical `api/dependencies.py` helpers | WARNING | WR-01 from review: `/health` uses `main.py` copies; router and tests use `api.dependencies` versions. Two distinct function objects mean overriding one does not affect the other. Future test that imports DI from wrong source will silently fail. |
| `api/routers/documents.py` | 177-193 | Failed re-enqueue branch calls `process_document.delay()` inside the open Neo4j session, unlike the brand-new branch | WARNING | WR-03 from review: inconsistent transaction boundary; a slow/failing disk write holds the session open longer; `delay()` inside session block vs. outside in new-doc branch is structurally inconsistent. |
| `api/routers/documents.py` | 127 | `data = await file.read()` reads full body before size check | INFO | WR-02 from review: cap is enforced post-read; a 2 GiB upload is spooled to disk before rejection — comment overstates memory protection. |
| `core/pipeline/tasks.py` | 79-86 | `glob("*.pdf")[0]` ignores `file_uri` stored on Document node | INFO | WR-04 from review: re-POST with different filename creates a second file; glob ordering is filesystem-dependent. Benign in practice (SHA-256 bytes are identical) but latent foot-gun. |

No stub patterns found. No `TODO`/`FIXME`/placeholder comments in production code. No `return null`/empty returns in business-logic paths.

---

### Human Verification Required

#### 1. Live end-to-end run confirming criterion #4

**Test:** With Neo4j running and `OPENROUTER_API_KEY` set, execute:
```
pytest tests/test_ingestion_e2e.py::test_ingestion_happy_path -v
```
**Expected:** PASSED. Processing status reaches "written". `find_candidates_by_skill` returns the ingested candidate. Dedup re-POST returns status 200 + `task_id: null`.

**Why human:** The test makes a live paid LLM call (~2 min, network). The SUMMARY self-check reports "2 passed in ~123s" but this cannot be confirmed programmatically by a verifier without running the test. This is the primary proof of ROADMAP criterion #4.

#### 2. CR-01 Risk Assessment: mid-pipeline Neo4j outage

**Test:** With Neo4j running, start a document ingestion (POST /documents with a real PDF and a running Celery worker), then stop Neo4j during the extract step, and observe the document's final state via GET /documents/{id}.

**Expected (current behavior):** `processing_status` will remain "processing" permanently because `set_failed()` itself cannot write to Neo4j when Neo4j is down. The D-05 dedup logic will then return 202/null for any subsequent POST of the same bytes, blocking re-ingestion without manual `DETACH DELETE` of the Document node.

**Expected (after CR-01 fix):** `processing_status` should transition to "failed" with `failed_stage` set — or at minimum, the exception should propagate such that the task is observably failed and the document is recoverable.

**Why human:** Cannot simulate a mid-pipeline database outage via static analysis. CR-01 is a tracked known issue (from 07-REVIEW.md) but is not fixed in the current codebase. The decision whether to accept this risk for the local v1 single-user MVP or require it fixed before marking the phase complete is a human judgment call.

---

### Noted Deviation: e2e Test Bypasses Celery Dispatch Layer

The 07-03 PLAN specified Celery eager mode (`task_always_eager=True`) as the worker strategy. The implementation instead:
1. Patches `api.routers.documents.process_document` with a no-op fake that captures `document_id` and returns `_EagerResult`
2. Calls `await _run(document_id)` directly in the test's event loop

This means `process_document` (the Celery sync wrapper, which calls `asyncio.run(_run(...))`) is never executed end-to-end. The `asyncio.run()` call and its interaction with the Celery worker's event loop are not tested.

**Why this is acceptable for goal verification:** The Celery sync wrapper contains no business logic — its sole purpose is to bridge sync Celery to the async `_run()` coroutine. The real pipeline body (parse→extract→write, status tracking, Neo4j writes) IS fully exercised. The deviation is documented as a Rule 1 Windows ProactorEventLoop platform constraint — a real technical limitation, not a shortcut. The unit test `test_process_document_task_name` confirms the Celery task is correctly decorated and named.

**What is NOT tested end-to-end:** The path `process_document.delay(id)` → Celery broker → worker picks up task → `asyncio.run(_run(id))` executes. This requires a real Redis broker and Celery worker running outside the test process.

---

### Gaps Summary

No gaps blocking the stated phase goal. All five success criteria have corresponding implementation. The primary uncertainty is human-gated: confirmation that `test_ingestion_happy_path` actually passes live (criterion #4).

The CR-01 BLOCKER from the code review (mid-pipeline Neo4j drop leaves document wedged in "processing") is a production correctness concern. It does not prevent the goal from being *demonstrated* via the test suite (unit tests mock GraphDB, e2e test runs against a stable Neo4j). However, it is a documented unaddressed defect in the production code that affects reliability of the `failed` status and the `failed_stage` contract under adverse conditions.

---

_Verified: 2026-06-14T20:00:00Z_
_Verifier: Claude (gsd-verifier)_
