---
phase: 03-test-data-eval
plan: "02"
subsystem: database
tags: [neo4j, cypher, async, neo4j-driver]

# Dependency graph
requires:
  - phase: 03-test-data-eval
    provides: "seed.py with candidate c-001 and all 12 node types wired into Neo4j"
provides:
  - "scripts/queries.py — three async Cypher search functions: find_candidates_by_skill, find_candidates_by_company, find_candidates_by_status"
affects: [03-03-eval-harness, tests]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure function library pattern: queries.py takes AsyncDriver directly, no GraphDB wrapper import"
    - "Parameterized Cypher with $param syntax, Cypher documented in docstrings"
    - "Case-insensitive matching via toLower() for fuzzy name searches"
    - "DISTINCT return in multi-hop traversal to deduplicate candidates"

key-files:
  created:
    - scripts/queries.py
  modified: []

key-decisions:
  - "AsyncDriver (not GraphDB wrapper) as function argument — keeps query library infrastructure-agnostic and usable in test fixtures directly"
  - "DISTINCT in find_candidates_by_company — prevents duplicating candidates with multiple experiences at same company"

patterns-established:
  - "Query library pattern: async functions accept driver, run parameterized Cypher, return list[dict]"
  - "Cypher relationship names follow core_architecture.md §4.3: HAS_SKILL, HAS_EXPERIENCE, AT_COMPANY, REACHED_STATUS, IN_VACANCY"

requirements-completed:
  - SEED-02

# Metrics
duration: 5min
completed: 2026-05-07
---

# Phase 3 Plan 02: Примеры Cypher-запросов Summary

**Three async Neo4j query functions (skill, company, status pipeline) in a pure driver-based library with parameterized Cypher and case-insensitive matching**

## Performance

- **Duration:** 5 min
- **Started:** 2026-05-07T11:00:00Z
- **Completed:** 2026-05-07T11:05:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Created `scripts/queries.py` as an infrastructure-free library of three async search functions
- All Cypher relationship names verified against `seed.py` (HAS_SKILL, HAS_EXPERIENCE, AT_COMPANY, REACHED_STATUS, IN_VACANCY)
- Module imports cleanly; all three functions importable individually

## Task Commits

Each task was committed atomically:

1. **Task 03-02-T1: Create scripts/queries.py** - `3c2fcad` (feat)

**Plan metadata:** (docs commit below)

## Files Created/Modified

- `scripts/queries.py` - Async Cypher query library: find_candidates_by_skill, find_candidates_by_company, find_candidates_by_status

## Decisions Made

- AsyncDriver (not GraphDB wrapper) as first argument — keeps the query library decoupled from infrastructure; test conftest fixtures can inject the driver directly without instantiating GraphDB.
- DISTINCT keyword in find_candidates_by_company — a candidate with multiple Experience nodes at the same company would otherwise appear multiple times in results.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `scripts/queries.py` is ready for use in the eval harness (plan 03-03)
- Three canonical search patterns established that the eval harness can call against live Neo4j seeded with `scripts/seed.py`

## Self-Check: PASSED

- FOUND: scripts/queries.py
- FOUND: commit 3c2fcad

---
*Phase: 03-test-data-eval*
*Completed: 2026-05-07*
