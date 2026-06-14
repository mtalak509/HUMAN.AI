---
phase: 07-ingestion-api
plan: 03
subsystem: testing
tags: [pytest, httpx, fastapi, neo4j, celery, asyncio, e2e]

# Dependency graph
requires:
  - phase: 07-01
    provides: process_document Celery task (_run coroutine), status helpers, STATUS_* constants
  - phase: 07-02
    provides: POST /documents + GET /documents/{id} endpoints, D-04/D-05/D-06 logic
  - phase: 06-graph-writer
    provides: GraphWriter.write() — tested end-to-end through the pipeline
  - phase: 05-llm-extractor
    provides: Extractor.extract() — exercised in happy path (live LLM call)
  - phase: 04-pdf-parser
    provides: PdfParser.parse() — exercised in both happy and failure paths

provides:
  - tests/test_ingestion_e2e.py: 2 e2e tests — happy path + failure path (criteria #4, #5)
  - ROADMAP criterion #4: real PDF -> find_candidates_by_skill confirms candidate in graph
  - ROADMAP criterion #5: dedup (written->200/null), failure diagnostics (D-06), re-enqueue (D-05)

affects:
  - future e2e tests (established httpx.AsyncClient + ASGITransport pattern for async Neo4j fixtures)

# Tech tracking
tech-stack:
  added: [httpx.AsyncClient with ASGITransport (async ASGI test client)]
  patterns:
    - "httpx.AsyncClient + ASGITransport replaces TestClient for async test contexts with session-scoped Neo4j fixtures (avoids 'Future attached to different loop' on Windows ProactorEventLoop)"
    - "await _run(document_id) directly in test instead of Celery eager mode (asyncio.run() conflict with running pytest-asyncio loop)"
    - "_FakeExtractor plain class (not AsyncMock) for cross-loop-safe monkeypatching in threaded contexts"
    - "_make_noop_delay captures document_id for direct _run() invocation pattern"

key-files:
  created:
    - tests/test_ingestion_e2e.py

key-decisions:
  - "httpx.AsyncClient + ASGITransport instead of TestClient: session-scoped async graph_db fixture's Neo4j driver is bound to the pytest-asyncio session loop; TestClient creates its own anyio event loop causing 'Future attached to different loop'"
  - "await _run(document_id) directly instead of Celery eager mode: asyncio.run() in the task body cannot be called from a running event loop; direct await executes the same real code (parse->extract->write) without the Celery sync wrapper"
  - "_FakeExtractor as a plain class (not AsyncMock): AsyncMock creates futures bound to the loop where it's created; when used in a thread context (eager mode testing) this causes cross-loop errors"
  - "No LLM call in failure path: _FakeExtractor injects RuntimeError deterministically (T-07-13 — CI-safe without OPENROUTER_API_KEY)"
  - "test_ingestion_happy_path is the only test requiring OPENROUTER_API_KEY; test_ingestion_failure_path requires Neo4j only"

requirements-completed: [API-01, API-02, PIPE-01]

# Metrics
duration: 14min
completed: 2026-06-14
---

# Phase 7 Plan 03: End-to-End Ingestion Test Summary

**POST /documents -> _run() pipeline (parse->extract->write) -> GET 'written' -> find_candidates_by_skill confirms candidate in graph, with D-05 dedup and D-06 failure diagnostics verified end-to-end**

## Performance

- **Duration:** 14 min
- **Started:** 2026-06-14T18:49:06Z
- **Completed:** 2026-06-14T19:03:20Z
- **Tasks:** 2 (both auto)
- **Files modified:** 1 (created)

## Accomplishments

- `tests/test_ingestion_e2e.py` with 2 e2e tests: happy path + failure path
- ROADMAP criterion #4 satisfied: real PDF ingested to Neo4j and found by `find_candidates_by_skill`
- ROADMAP criterion #5 satisfied: D-05 dedup (written -> 200/null, failed -> re-enqueue), D-06 diagnostics
- Both tests skip cleanly without infra (happy path also skips without OPENROUTER_API_KEY)
- Phase 7 Ingestion API complete: all 3 plans done

## Task Commits

1. **Tasks 1 + 2: E2E happy path + dedup + failure path** - `01e36e6` (feat)

## Files Created/Modified

- `tests/test_ingestion_e2e.py` — 2 e2e integration tests: happy path + failure path

## Decisions Made

- **`httpx.AsyncClient + ASGITransport` instead of `TestClient`**: Session-scoped async `graph_db` fixture creates a Neo4j driver on the pytest-asyncio session event loop. `TestClient` (Starlette) creates its own anyio event loop internally — the route handler then tries to use `graph_db`'s driver which is bound to a different loop, causing `RuntimeError: Task got Future attached to different loop`. `httpx.AsyncClient` with `ASGITransport` runs the ASGI app in the same event loop as the test, fully eliminating this conflict.

- **`await _run(document_id)` directly instead of Celery eager mode**: The plan specifies Celery eager mode (`task_always_eager=True`) as the worker strategy. In practice, Celery's sync task wrapper calls `asyncio.run(_run(...))` which raises `RuntimeError: asyncio.run() cannot be called from a running event loop`. All three attempted approaches (nest_asyncio, background thread + asyncio.run, SelectorEventLoop in thread) failed: nest_asyncio exposed ProactorEventLoop teardown bugs; ThreadPoolExecutor + asyncio.run caused "Future attached to different loop" due to Neo4j async driver's loop-affinity; SelectorEventLoop also failed. Direct `await _run(document_id)` in the test's event loop is semantically equivalent to eager mode: the real task code (parse->extract->write) runs in the same process, uses the same Neo4j, and the orchestration is fully exercised.

- **`_FakeExtractor` as a plain class, not `AsyncMock`**: `AsyncMock` creates coroutine objects whose internal futures are bound to the loop that instantiated the mock. When the failure-path test passes `Extractor` to `_run()` (which in production runs in a worker process with its own loop), there would be loop cross-contamination. A plain `async def extract(...)` method on a plain class creates a fresh coroutine object on each call, bound to whichever loop awaits it — cross-loop safe.

- **`task_always_eager = True` still set (for consistency)**: Even though the test calls `_run()` directly, `celery_app.conf.task_always_eager = True` is set in both tests to document the intent and to ensure the `process_document.delay()` call in the POST handler returns an `EagerResult`-like object (our `_EagerResult` from `_make_noop_delay`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Replaced TestClient with httpx.AsyncClient + ASGITransport**
- **Found during:** Task 1 (initial test implementation)
- **Issue:** `TestClient` creates its own anyio event loop; session-scoped `graph_db` Neo4j driver is bound to the pytest-asyncio session loop; combining them causes `RuntimeError: Task got Future <Future pending> attached to a different loop` on every POST/GET through the router
- **Fix:** Used `httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")` which runs the ASGI app on the test's own event loop — same loop as `graph_db`
- **Files modified:** tests/test_ingestion_e2e.py
- **Verification:** `pytest tests/test_ingestion_e2e.py -v` → 2 passed (both tests)
- **Committed in:** 01e36e6

**2. [Rule 1 - Bug] Replaced Celery eager mode with direct `await _run(document_id)`**
- **Found during:** Task 1 (eager mode investigation)
- **Issue:** Celery's `process_document` calls `asyncio.run(_run(...))`. This cannot be called from within a running event loop (pytest-asyncio holds one). Three bypass strategies tried (nest_asyncio, ThreadPoolExecutor + asyncio.run, SelectorEventLoop in thread) all failed: nest_asyncio broke ProactorEventLoop teardown; thread approach caused "Future attached to different loop" in the Neo4j async driver; SelectorEventLoop had the same cross-loop issue
- **Fix:** Intercepted `process_document.delay()` with `_make_noop_delay()` (captures `document_id`, returns `_EagerResult`) and then directly `await _run(document_id)`. This executes the real parse->extract->write pipeline code against the same Neo4j
- **Files modified:** tests/test_ingestion_e2e.py
- **Verification:** Happy path completes parse->extract->write (2 min LLM call), status becomes "written"; failure path injects RuntimeError into Extractor, status becomes "failed"
- **Committed in:** 01e36e6

**3. [Rule 1 - Bug] Used plain `_FakeExtractor` class instead of `AsyncMock` for Extractor monkeypatch**
- **Found during:** Task 2 (failure path implementation)
- **Issue:** `AsyncMock(side_effect=RuntimeError(...))` creates internal futures tied to the instantiating loop; when awaited inside `_run()` (on the test's session loop), produced "Future attached to different loop"
- **Fix:** Defined `_FakeExtractor` as a plain class with `async def extract(...)` raising RuntimeError. Each call creates a fresh coroutine with no pre-bound futures
- **Files modified:** tests/test_ingestion_e2e.py
- **Verification:** `pytest tests/test_ingestion_e2e.py::test_ingestion_failure_path -v` → PASSED
- **Committed in:** 01e36e6

---

**Total deviations:** 3 auto-fixed (all Rule 1 — platform-specific async/event-loop incompatibilities on Windows ProactorEventLoop)
**Impact on plan:** All three fixes are workarounds for the same root cause: Windows ProactorEventLoop has stricter cross-loop enforcement than Linux epoll. The test fully exercises the plan's intent: the real pipeline code runs, the real Neo4j is written to, the real API routes are tested via HTTP. Only the Celery sync wrapper is bypassed, which is not meaningful in a test context (it exists to bridge sync Celery to async Python, not for business logic).

## Issues Encountered

- **Windows ProactorEventLoop cross-loop compatibility**: On Windows, the `asyncio.ProactorEventLoop` (default since Python 3.8) enforces strict event-loop affinity for futures and tasks. Any attempt to share futures across loops (via `nest_asyncio`, background threads, or `asyncio.run()` from within a running loop) fails. The solution is to keep all async Neo4j operations on the same event loop — achieved with `httpx.AsyncClient + ASGITransport` and direct `await _run()`.

## Known Stubs

None — all assertions are against real data from the live pipeline.

## Threat Flags

No new security surface. This is a test-only file.

## Next Phase Readiness

Phase 7 Ingestion API is COMPLETE (07-01 ✅ 07-02 ✅ 07-03 ✅):
- `POST /documents` -> pipeline -> Neo4j graph: proven end-to-end
- `find_candidates_by_skill` confirmed working post-ingestion
- D-05 dedup and D-06 failure diagnostics verified
- All 3 requirements marked complete: API-01, API-02, PIPE-01

---
*Phase: 07-ingestion-api*
*Completed: 2026-06-14*
