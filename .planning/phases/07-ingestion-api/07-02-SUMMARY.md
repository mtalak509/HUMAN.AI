---
phase: 07-ingestion-api
plan: 02
subsystem: api
tags: [fastapi, upload, multipart, celery, neo4j, dedup, status-api]

# Dependency graph
requires:
  - phase: 07-01
    provides: process_document.delay, merge_document_queued, reset_for_requeue, STATUS_* constants
  - phase: 04-pdf-parser
    provides: SHA-256 document_id formula (hashlib.sha256(bytes).hexdigest())
  - phase: 06-graph-writer
    provides: GraphDB.is_connected / session() DI pattern

provides:
  - api/dependencies.py: get_db / get_settings FastAPI DI helpers (shared, circular-import safe)
  - api/routers/documents.py: POST /documents + GET /documents/{id} router
  - api/main.py: app.include_router(documents.router) registration
  - tests/test_documents_api_unit.py: 14 unit tests, no infra required

affects:
  - 07-03 e2e test (POST /documents is the entry point for end-to-end flow)
  - any future auth middleware (routes are now registered and discoverable)

# Tech tracking
tech-stack:
  added: [python-multipart (already installed; UploadFile multipart dependency)]
  patterns:
    - "TDD: RED (14 failing tests) -> GREEN (full implementation)"
    - "api/dependencies.py DI module — breaks circular import between api/main.py and api/routers/"
    - "D-04: merge_document_queued called inside session block BEFORE process_document.delay (outside block)"
    - "D-05 dedup: written->200/null, queued|processing->202/null, failed->reset_for_requeue+202/task_id"
    - "D-06: GET returns processing_status+error+failed_stage; reset_for_requeue clears stale diagnostics on re-enqueue"
    - "T-07-06: MAX_UPLOAD_BYTES=10MiB cap; T-07-07: Path(filename).name traversal guard; T-07-08: .pdf suffix+content-type"
    - "T-07-09: document_id used only as bound $param in MATCH (no Cypher injection)"

key-files:
  created:
    - api/dependencies.py
    - api/routers/__init__.py
    - api/routers/documents.py
    - tests/test_documents_api_unit.py
  modified:
    - api/main.py (added include_router + late import of documents router)

key-decisions:
  - "api/dependencies.py introduced to avoid circular import (api/main.py imports router, router needs DI helpers)"
  - "D-04 ordering: merge_document_queued inside async-with-session, process_document.delay AFTER session closes"
  - "D-05 dedup: _read_status helper runs inside the same session before any write — single round trip"
  - "failed branch uses reset_for_requeue (not merge_document_queued ON CREATE SET) to guarantee stale error/failed_stage cleared"
  - "413 status code used as literal int (not status.HTTP_413_REQUEST_ENTITY_TOO_LARGE which is deprecated in FastAPI)"

# Metrics
duration: 6min
completed: 2026-06-14
---

# Phase 7 Plan 02: HTTP Ingestion API Summary

**POST /documents + GET /documents/{id} over FastAPI with D-04 MERGE-before-enqueue, D-05 status-smart dedup, D-06 error/failed_stage exposure, and four security mitigations (T-07-06/07/08/09)**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-06-14T18:38:38Z
- **Completed:** 2026-06-14T18:44:41Z
- **Tasks:** 2 (both TDD)
- **Files modified:** 5 (4 created, 1 modified)

## Accomplishments

- `api/dependencies.py` — shared DI helpers (`get_db`, `get_settings`) avoiding circular import
- `api/routers/documents.py` — full POST + GET implementation:
  - POST: SHA-256 id derivation (same as PdfParser), 10MiB cap, .pdf validation, file save, `merge_document_queued` BEFORE enqueue (D-04), D-05 dedup all four branches
  - GET: `_read_status` Cypher helper, returns status+error+failed_stage or 404 (D-06)
- `api/main.py` updated with `app.include_router(documents.router)`
- 14 unit tests across all branches — all green, no infra required

## Task Commits

1. **TDD RED: failing tests for POST + GET** - `ecc3d14` (test)
2. **GREEN: full implementation** - `7f51077` (feat)

## Files Created/Modified

- `api/dependencies.py` — `get_db` / `get_settings` DI functions (new module, solves circular import)
- `api/routers/__init__.py` — package marker
- `api/routers/documents.py` — POST /documents + GET /documents/{document_id} router
- `tests/test_documents_api_unit.py` — 14 unit tests: all POST branches + GET scenarios
- `api/main.py` — added `app.include_router(documents.router)` with late import

## Decisions Made

- **`api/dependencies.py`**: router needed `get_db`/`get_settings` but importing from `api.main` would be circular (`api.main` imports the router). Extracted DI helpers to `api/dependencies.py`; both `api/main.py` and router import from there. Tests import `get_db`/`get_settings` from `api.dependencies` for override key consistency.
- **`process_document.delay` AFTER session closes**: D-04 requires MERGE before enqueue. Session is opened, MERGE runs, session closes, then `.delay()` fires — ensuring the Document node exists before the worker picks up the task.
- **`_read_status` single Cypher query**: returns `None` for brand-new or dict for existing — one round-trip covers all dedup branches.
- **`reset_for_requeue` for failed re-enqueue**: `merge_document_queued` uses `ON CREATE SET` so it would be a no-op on an existing (failed) node. `reset_for_requeue` explicitly sets status=queued AND clears error/failed_stage — D-06 freshness guaranteed.
- **413 as int literal**: `status.HTTP_413_REQUEST_ENTITY_TOO_LARGE` is deprecated in FastAPI in favor of `HTTP_413_CONTENT_TOO_LARGE`; used `413` directly to avoid the DeprecationWarning.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Circular import between api/main.py and api/routers/documents.py**
- **Found during:** Task 1 implementation
- **Issue:** Plan specified `from api.main import get_db, get_settings` in the router, but `api/main.py` imports the router. Circular import prevents module loading.
- **Fix:** Created `api/dependencies.py` with the DI helpers; router imports from there. `api/main.py` uses a late import (`from api.routers import documents` after `app = FastAPI(...)`) with `# noqa: E402`. Tests updated to `from api.dependencies import get_db, get_settings`.
- **Files modified:** api/dependencies.py (new), api/routers/documents.py, api/main.py, tests/test_documents_api_unit.py
- **Committed in:** 7f51077

**2. [Rule 1 - Bug] HTTP 413 DeprecationWarning in FastAPI**
- **Found during:** Task 1 GREEN phase (pytest warning)
- **Issue:** `status.HTTP_413_REQUEST_ENTITY_TOO_LARGE` emits a DeprecationWarning in FastAPI's routing layer
- **Fix:** Used literal `413` instead of the deprecated constant
- **Files modified:** api/routers/documents.py
- **Committed in:** 7f51077

---

**Total deviations:** 2 auto-fixed (both Rule 1 — circular import + deprecation warning)
**Impact on plan:** No scope change. The `api/dependencies.py` module is a cleaner architecture than importing DI from `api.main` anyway.

## Known Stubs

None — no stub values or placeholder data.

## Threat Flags

No new security surface beyond the plan's threat model. All 5 threats addressed:
- T-07-06: MAX_UPLOAD_BYTES=10MiB + empty=400 guards in POST
- T-07-07: `safe_name = Path(filename).name` before every `write_bytes` call
- T-07-08: `.pdf` suffix + content-type in `_ACCEPTED_CONTENT_TYPES` validated at route entry
- T-07-09: document_id only appears as `$document_id` bound param in `_READ_STATUS_CYPHER`
- T-07-10: no rate limiting (accepted, documented in plan)

## Next Phase Readiness

- `python -c "from api.main import app; print([r.path for r in app.routes if 'documents' in r.path])"` lists `['/documents', '/documents/{document_id}']`
- 07-03 e2e test can POST to `/documents` with a real PDF and poll GET `/documents/{id}`
- No auth layer — acceptable for local v1 single-user MVP (T-07-10 accepted)

---
*Phase: 07-ingestion-api*
*Completed: 2026-06-14*
