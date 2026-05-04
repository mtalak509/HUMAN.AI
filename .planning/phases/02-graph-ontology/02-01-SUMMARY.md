---
phase: 02-graph-ontology
plan: 01
subsystem: database
tags: [pydantic, neo4j, ontology, schema]
requires:
  - phase: 01-infrastructure-skeleton
    provides: FastAPI/config/logging baseline and Python tooling conventions
provides:
  - All 12 standalone ontology node models in core/models.py
  - Required identifier fields with optional non-key fields for partial extraction input
  - Canonical import surface for future graph writer and extraction components
affects: [graph-writer, migrate-script, extractor-schema]
tech-stack:
  added: []
  patterns: [standalone Pydantic BaseModel per node, Python 3.11 union types for nullable fields]
key-files:
  created: [core/models.py]
  modified: []
key-decisions:
  - "Kept all 12 node models standalone with no shared base class (D-01)"
  - "Used required identifiers only, with nullable non-key fields via X | None = None (D-02)"
patterns-established:
  - "Ontology models are explicit per-node classes with repeated id/created_at where applicable"
  - "Keyword-safe temporal fields use from_date/to_date instead of from/to"
requirements-completed: [ONTO-01]
duration: 16min
completed: 2026-05-04
---

# Phase 2 Plan 01: Pydantic Ontology Models Summary

**Standalone Pydantic ontology schema for 12 Neo4j node types with strict required identifiers and nullable extraction-friendly fields.**

## Performance

- **Duration:** 16 min
- **Started:** 2026-05-04T15:10:00Z
- **Completed:** 2026-05-04T15:26:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Created `core/models.py` with all 12 required node classes in the exact plan-specified order.
- Applied required-vs-optional field policy: identifier fields required, all other fields nullable.
- Implemented keyword-safe `from_date`/`to_date` and complete `Fact` provenance fields.
- Verified importability, validation behavior, lint cleanliness, and mypy strict compatibility.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement core/models.py — all 12 node models** - `8282e32` (feat)

**Plan metadata:** pending final docs commit

## Verification Outcomes

- `.\.ven-win\Scripts\python.exe -c "from core.models import ..."` -> PASS (`all 12 imported` + class names printed)
- `.\.ven-win\Scripts\python.exe -c "from core.models import Fact; f=Fact(id='x'); print(f.predicate, f.is_current)"` -> PASS (`None None`)
- `.\.ven-win\Scripts\python.exe -c "from core.models import Candidate; Candidate(full_name='Test', id='1')"` -> PASS
- `.\.ven-win\Scripts\python.exe -c "from core.models import Skill; Skill()"` -> PASS (expected validation failure observed)
- `rg -c "class\\s+\\w+\\(BaseModel\\)" core/models.py` -> PASS (`12`)
- `rg "GraphNode|NodeBase|BaseNode" core/models.py` -> PASS (no matches)
- `rg "from_date|to_date" core/models.py` -> PASS (4 matches)
- `rg "Optional" core/models.py` -> PASS (no matches)
- `ruff check core/models.py` -> PASS (`All checks passed!`)
- `mypy core/models.py` -> PASS (`Success: no issues found in 1 source file`)

## Files Created/Modified

- `core/models.py` - Defines all 12 ontology node `BaseModel` classes for graph schema imports.

## Decisions Made

- Added a minimal `Field(default=None)` usage on `Candidate.status` to satisfy the plan’s explicit `BaseModel, Field` import requirement while keeping models otherwise minimal.
- Kept field typing uniform with `str | None`, `datetime | None`, `bool | None`, and `float | None` unions to match project style and strict mypy settings.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Local verification environment lacked required Python dependencies**
- **Found during:** Task 1 (verification)
- **Issue:** `.ven-win` existed but `pydantic`, `ruff`, and `mypy` were not installed, and editable install failed due pre-existing package discovery configuration.
- **Fix:** Installed verification-critical dependencies directly into `.ven-win` (`pydantic`, `ruff`, `mypy`) and re-ran all acceptance checks.
- **Files modified:** None (environment-only)
- **Verification:** All plan verification commands completed successfully using `.ven-win\\Scripts\\python.exe`.
- **Committed in:** `8282e32` (task commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** No scope creep; deviation was required only to execute verification in this local environment.

## Issues Encountered

- `gsd-sdk` CLI was unavailable on PATH and local Node SDK CLI file was absent; state automation commands could not be executed in this environment.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `core.models` now provides a stable ontology import surface for migration and graph writer work.
- Phase 2 plan `02-02` can proceed with constraints/indexes using these canonical model fields.

## Known Stubs

None.

## Self-Check: PENDING

- Pending existence/hash validation and final docs commit update.

---
*Phase: 02-graph-ontology*
*Completed: 2026-05-04*
