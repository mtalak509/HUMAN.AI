---
phase: 02-graph-ontology
plan: 02
subsystem: database
tags: [neo4j, cypher, pydantic-settings, loguru, asyncio]

requires:
  - phase: 02-graph-ontology
    provides: Graph ontology node labels and key properties (from 02-01 / CONTEXT)
provides:
  - Idempotent DDL script `scripts/migrate.py` for all ontology node types
  - UNIQUE constraints and search indexes aligned with plan 02-02
affects:
  - ingestion-pipeline
  - graph-writes

tech-stack:
  added: []
  patterns:
    - "Standalone migration: `python scripts/migrate.py` using `get_settings()` + `GraphDB`"
    - "Neo4j 5.x DDL: `CREATE CONSTRAINT ... IF NOT EXISTS` / `CREATE INDEX ... IF NOT EXISTS`"

key-files:
  created:
    - scripts/migrate.py
    - scripts/__init__.py
    - core/database/graph.py
  modified:
    - core/graph.py
    - core/config.py

key-decisions:
  - "Kept `from core.graph import GraphDB` in the migration script per plan; implemented `core/graph.py` as a thin re-export over `core.database.graph` so the canonical driver stays under `core/database/` (matches CLAUDE.md layout and local `api/main` experiments)."
  - "Wrapped `connect_with_retry`, session work, and `db.close()` in one `try`/`finally` so the driver is closed when Neo4j is unreachable (driver is still constructed before ping failures)."

patterns-established:
  - "Schema stamping: run `python scripts/migrate.py` before writers touch the graph; safe to repeat in CI."

requirements-completed: [ONTO-02]

duration: ~22min
completed: 2026-05-04
---

# Phase 02 Plan 02: Neo4j schema migration Summary

**Idempotent Neo4j 5.x DDL script applying twelve UNIQUE constraints (one per ontology node label) and four partial indexes on hot lookup fields, driven by `get_settings()` and `GraphDB.connect_with_retry`.**

## Performance

- **Duration:** ~22 min
- **Started:** 2026-05-04T19:45:00Z (approx.)
- **Completed:** 2026-05-04T20:02:00Z (approx.)
- **Tasks:** 1
- **Files modified:** 5 (in task commit)

## Accomplishments

- Added `scripts/migrate.py` with `asyncio.run(main())`, structured logging, and `sys.exit(1)` when the graph is unreachable after retries.
- Applied all planned constraints and indexes with `IF NOT EXISTS`; verified a second run completes with exit code 0 against Docker Neo4j.
- Confirmed `SHOW CONSTRAINTS` returns 12 rows for this migration; `SHOW INDEXES` includes `candidate_full_name_idx` and `fact_predicate_idx`.

## Task Commits

1. **Task 1: Create scripts/migrate.py with idempotent constraints and indexes** — `5e5985c` (feat)

**Plan metadata:** Docs commit bundles this SUMMARY with `.planning/STATE.md`, `.planning/ROADMAP.md`, and `.planning/REQUIREMENTS.md`. `gsd-sdk` was not available in this workspace — no automated `state.advance-plan` / `requirements.mark-complete` CLI runs beyond those manual edits.

## Files Created/Modified

- `scripts/migrate.py` — Applies all ontology UNIQUE constraints and the four search indexes; closes the driver in `finally`.
- `scripts/__init__.py` — Empty package marker for `scripts`.
- `core/database/graph.py` — Async Neo4j `GraphDB` wrapper (connect with retry, session context manager, `close`).
- `core/graph.py` — Re-exports `GraphDB` for the import path required by the plan and backward compatibility.
- `core/config.py` — `type: ignore[call-arg]` on `Settings()` so strict `mypy` accepts env-backed `neo4j_password`.

## Decisions Made

- Chose a `core.graph` → `core.database.graph` re-export instead of changing the plan’s required import string in `scripts/migrate.py`.
- Extended `try`/`finally` around connection as well as DDL so `close()` runs after connection failures (deviation from the plan snippet ordering, for resource safety).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Canonical `GraphDB` path vs. plan import**

- **Found during:** Task 1 (implementation)
- **Issue:** The repository already moved the driver implementation to `core/database/graph.py` while the plan still mandates `from core.graph import GraphDB`.
- **Fix:** Added `core/graph.py` as a re-export and committed `core/database/graph.py`; applied `ruff check --fix` on the driver file for import order / `collections.abc.AsyncGenerator`.
- **Files modified:** `core/graph.py`, `core/database/graph.py`
- **Verification:** `python scripts/migrate.py` (twice) against live Neo4j; `ruff` / `mypy` clean on touched modules.
- **Committed in:** `5e5985c`

**2. [Rule 2 — Missing critical / Rule 3 — Blocking] Strict `mypy` on `get_settings()`**

- **Found during:** Task 1 (`mypy scripts/migrate.py`)
- **Issue:** `return Settings()` flagged `call-arg` for required `neo4j_password` despite runtime population from `.env`.
- **Fix:** Added `# type: ignore[call-arg]` with a short rationale comment on `get_settings()`.
- **Files modified:** `core/config.py`
- **Verification:** `mypy scripts/migrate.py core/graph.py core/database/graph.py` exits 0.
- **Committed in:** `5e5985c`

**3. [Rule 2 — Correctness] Driver shutdown when Neo4j never connects**

- **Found during:** Task 1 (code review)
- **Issue:** With the plan’s `try` only around the session block, `sys.exit(1)` on `not db.is_connected` skipped `await db.close()` even though `AsyncGraphDatabase.driver` was already created.
- **Fix:** Wrapped `connect_with_retry`, session DDL, and `close()` in a single outer `try`/`finally`.
- **Files modified:** `scripts/migrate.py`
- **Verification:** Re-ran migration after the change; idempotent second run still passes.
- **Committed in:** `5e5985c`

---

**Total deviations:** 3 (all auto-fixed; 1 blocking import/layout, 1 typing unblock, 1 resource lifecycle)

**Impact on plan:** No change to Cypher surface or constraint/index names; behavior matches success criteria and must-haves.

## Issues Encountered

- None beyond the deviations above.

## User Setup Required

None for code review. To reproduce live checks: copy `.env.example` → `.env`, set `NEO4J_PASSWORD`, run `docker compose up -d neo4j`, then `python scripts/migrate.py` from the repo root with the virtualenv activated.

## Next Phase Readiness

- Neo4j schema can be stamped in CI or before app startup; writers can rely on named constraints for `MERGE` keys.
- Optional: wire `scripts/migrate.py` into Docker `fastapi` `depends_on` health or a dedicated init job when orchestration is defined.

---

*Phase: 02-graph-ontology*

*Completed: 2026-05-04*

## Self-Check: PASSED

- `scripts/migrate.py` — present on disk.
- `git log --oneline -3` on `main` includes `feat(02-graph-ontology-02): add idempotent Neo4j schema migration script` and `docs(02-graph-ontology-02): complete graph ontology migration plan`.
