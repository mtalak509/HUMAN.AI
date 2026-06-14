---
phase: 07-ingestion-api
plan: 01
subsystem: api
tags: [celery, redis, neo4j, pipeline, async, ingestion]

# Dependency graph
requires:
  - phase: 04-pdf-parser
    provides: PdfParser.parse() + ParseResult + Document MERGE pattern
  - phase: 05-llm-extractor
    provides: Extractor.extract() + ExtractedCandidate
  - phase: 06-graph-writer
    provides: GraphWriter.write() with graceful degradation

provides:
  - core/pipeline/status.py: STATUS_* constants + merge_document_queued/set_status/set_failed/reset_for_requeue Cypher helpers
  - core/pipeline/celery_app.py: Celery app with Redis broker, no result backend (D-03)
  - core/pipeline/tasks.py: process_document Celery task — parse->extract->write orchestration
  - Document model: processing_status/error/failed_stage fields (D-01/D-06)
  - migrations.py: document_processing_status_idx index

affects:
  - 07-02 API endpoints (use merge_document_queued, process_document.delay)
  - 07-03 e2e test (end-to-end pipeline execution via broker)

# Tech tracking
tech-stack:
  added: [celery==5.6.3 (already installed), core.pipeline package]
  patterns:
    - "TDD for all 3 tasks: RED (failing tests) -> GREEN (implementation) -> REFACTOR (cleanup)"
    - "scripts-pattern GraphDB construction in Celery worker (get_settings() direct call, not FastAPI Depends)"
    - "Neo4j-down guard: is_connected=False raises BEFORE any pipeline step (T-07-03)"
    - "Per-stage failed_stage attribution: parse|extract|write (D-06)"
    - "Parameterized Cypher only in status helpers (T-07-01, no f-strings)"
    - "Celery task wraps asyncio.run(_run()) — sync outer, async inner"

key-files:
  created:
    - core/pipeline/__init__.py
    - core/pipeline/status.py
    - core/pipeline/celery_app.py
    - core/pipeline/tasks.py
    - tests/test_pipeline_status_unit.py
    - tests/test_pipeline_task_unit.py
  modified:
    - core/schemas/models.py (Document: +processing_status/error/failed_stage)
    - core/database/migrations.py (INDEXES: +document_processing_status_idx)

key-decisions:
  - "D-03: NO Celery result backend — processing_status on Neo4j Document node is sole source of truth"
  - "D-07: Fail-fast — no Celery autoretry_for; extractor's own 1-retry is preserved"
  - "D-06: per-stage failed_stage (parse|extract|write) + truncated error text ([:2000]) stored on Document"
  - "T-07-03: Neo4j-down raises before parse/extract/write — never silent success"
  - "merge_document_queued uses ON CREATE SET so re-POST of in-flight document does not overwrite processing status (D-05)"
  - "reset_for_requeue clears error/failed_stage to null for D-06 freshness on re-enqueue"

patterns-established:
  - "Pipeline status helpers: caller opens and passes AsyncSession — helpers run one parameterized statement each"
  - "Celery task = sync wrapper calling asyncio.run(async_orchestrator) — mirrors PdfParser run_in_executor pattern"
  - "Worker GraphDB: built via get_settings() direct call (scripts pattern, not FastAPI Depends)"

requirements-completed: [PIPE-01]

# Metrics
duration: 7min
completed: 2026-06-14
---

# Phase 7 Plan 01: Ingestion Pipeline Backbone Summary

**Celery `process_document` task with Neo4j-backed status tracking (queued/processing/written/failed), fail-fast per-stage error attribution, and parameterized Cypher helpers — wiring existing parse->extract->write components into an async pipeline**

## Performance

- **Duration:** 7 min
- **Started:** 2026-06-14T18:27:01Z
- **Completed:** 2026-06-14T18:34:09Z
- **Tasks:** 3 (all TDD)
- **Files modified:** 8 (6 created, 2 modified)

## Accomplishments

- `core/pipeline/` package with Celery app (redis broker, no result backend D-03) and `process_document` task
- Neo4j status helpers: `merge_document_queued` / `set_status` / `set_failed` / `reset_for_requeue` — all parameterized Cypher, T-07-01 compliant
- Document model extended with `processing_status` / `error` / `failed_stage`; `document_processing_status_idx` added to migrations
- 17 unit tests across two test files; all green, no infra required

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend Document model + add status index** - `c08baa3` (feat)
2. **Task 2: Status Cypher helpers + Celery app** - `48bae51` (feat)
3. **Task 3: process_document task** - `d7d77a9` (feat)

## Files Created/Modified

- `core/schemas/models.py` — Document model: +processing_status / error / failed_stage (Phase 7 fields, D-01/D-06)
- `core/database/migrations.py` — INDEXES: +document_processing_status_idx for future failed-doc list queries
- `core/pipeline/__init__.py` — package marker
- `core/pipeline/status.py` — STATUS_QUEUED/PROCESSING/WRITTEN/FAILED constants + 4 async Cypher helpers
- `core/pipeline/celery_app.py` — Celery("human_ai") with Redis broker, no result backend (D-03)
- `core/pipeline/tasks.py` — `_run()` async orchestrator + `process_document` Celery task (fail-fast D-07)
- `tests/test_pipeline_status_unit.py` — 11 unit tests: Document model, INDEXES, constants, Celery config
- `tests/test_pipeline_task_unit.py` — 6 unit tests: success path, extract failure, Neo4j-down guard, task name, no autoretry

## Decisions Made

- `process_document` uses `asyncio.run(_run())` — sync Celery outer, async inner — consistent with PdfParser's run_in_executor pattern
- `merge_document_queued` uses `ON CREATE SET` (not `SET`) so re-POST of an in-flight document does not clobber its current processing status (D-05 behavior)
- `@celery_app.task(name="process_document")` with `# type: ignore[untyped-decorator]` — mypy cannot infer Celery decorator type; the type ignore is scoped to this one annotation
- Pre-existing mypy errors in `core/writer/graph_writer.py` (`_write_tx` untyped params, tuple type args) are out of scope — logged as deferred

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed unused `pathlib.Path` import in tasks.py**
- **Found during:** Task 3 (process_document implementation)
- **Issue:** `from pathlib import Path` was imported but not used (ruff F401)
- **Fix:** Removed the import
- **Files modified:** core/pipeline/tasks.py
- **Verification:** `ruff check core/pipeline/` passes
- **Committed in:** d7d77a9 (Task 3 commit)

**2. [Rule 1 - Bug] Fixed pytest warnings — removed module-level `pytestmark = pytest.mark.asyncio`**
- **Found during:** Task 3 test cleanup (REFACTOR phase)
- **Issue:** `pytestmark = pytest.mark.asyncio` at module level applied `asyncio` mark to sync test functions, generating PytestWarning for each
- **Fix:** Removed `pytestmark` global; added `@pytest.mark.asyncio` individually to each async test
- **Files modified:** tests/test_pipeline_task_unit.py
- **Verification:** `pytest tests/test_pipeline_task_unit.py -q` passes with 0 warnings
- **Committed in:** d7d77a9 (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 — minor bugs caught by ruff/pytest)
**Impact on plan:** Both fixes necessary for clean tooling output. No scope creep.

## Issues Encountered

- mypy `[untyped-decorator]` error on `@celery_app.task` — Celery's task decorator does not expose full type information. Resolved with scoped `# type: ignore[untyped-decorator]`. The pre-existing `graph_writer.py` mypy errors are out of scope.

## Known Stubs

None — no stub values or placeholder data in pipeline code.

## Threat Flags

No new security-relevant surface beyond what is in the plan's threat model. All 5 threats (T-07-01 through T-07-05) are mitigated in implementation:
- T-07-01: Parameterized Cypher throughout status.py (verified via grep)
- T-07-02: document_id re-derived by PdfParser from actual bytes
- T-07-03: is_connected guard raises before any pipeline step
- T-07-04: error truncated to 2000 chars
- T-07-05: failed_stage recorded on Document node

## Next Phase Readiness

- `process_document` task is importable and runnable: `python -c "from core.pipeline.tasks import process_document; print(process_document.name)"`
- 07-02 (API endpoints) can import `process_document.delay(document_id)` and `merge_document_queued` directly
- 07-03 (e2e) needs a running Celery worker + Redis + Neo4j

---
*Phase: 07-ingestion-api*
*Completed: 2026-06-14*
