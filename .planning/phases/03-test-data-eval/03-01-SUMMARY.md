---
phase: 03-test-data-eval
plan: "01"
subsystem: database
tags: [neo4j, cypher, seed, test-data, graph, ontology]

requires:
  - phase: 02-graph-ontology
    provides: migrate.py schema with 12 node-type constraints; GraphDB, get_settings() patterns

provides:
  - scripts/seed.py — idempotent seed script loading candidate c-001 with all 12 node types
  - Full candidate graph in Neo4j: Алексей Соколов with skills, experience, education, vacancy, status, HRNote, documents, fact provenance

affects: [03-02-queries, 03-03-eval]

tech-stack:
  added: []
  patterns:
    - "MERGE-on-key idempotent node upsert: MERGE (n:NodeType {id: $id}) ON CREATE SET ... ON MATCH SET ..."
    - "Parameterised relationship MERGE: MATCH both ends then MERGE (a)-[:REL]->(b)"
    - "Fact provenance chain: Candidate -[:HAS_FACT]-> Fact -[:EXTRACTED_FROM]-> Document AND Fact -[:SUPPORTS]-> target"

key-files:
  created:
    - scripts/seed.py
  modified: []

key-decisions:
  - "All 12 node types instantiated in a single candidate to exercise the full ontology"
  - "MERGE keys mirror migrate.py constraints: Candidate/Contact/Experience/Education/Vacancy/Status/HRNote/Document/Fact by .id; Skill by .name; Company by .name; Role by .title"
  - "Fact nodes carry both EXTRACTED_FROM (Document) and SUPPORTS (target node) edges, validating provenance pattern"

patterns-established:
  - "Seed structure mirrors migrate.py: asyncio.run(main()), GraphDB, get_settings(), session.run()"
  - "Nodes seeded first, relationships wired second — prevents MATCH misses"

requirements-completed: [SEED-01]

duration: 2min
completed: 2026-05-07
---

# Phase 3 Plan 01: Seed Script Summary

**Idempotent Neo4j seed script loading Senior Python/ML engineer Алексей Соколов (c-001) across all 12 ontology node types with full fact-provenance chain**

## Performance

- **Duration:** 2 min
- **Started:** 2026-05-07T10:49:15Z
- **Completed:** 2026-05-07T10:50:34Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Created `scripts/seed.py` following `migrate.py` structure exactly (asyncio.run, GraphDB, get_settings)
- All 12 node types instantiated: Candidate, Contact, Skill (x5), Company (x2), Role (x2), Experience (x2), Education, Vacancy, Status, HRNote, Document, Fact (x2)
- Full relationship graph wired: 14 relationship types, including provenance chain HAS_FACT -> EXTRACTED_FROM -> Document and Fact -[:SUPPORTS]-> target node
- Script is fully idempotent — all nodes use MERGE with appropriate unique key per constraints in migrate.py

## Task Commits

1. **Task 1: Create scripts/seed.py** - `cd7627f` (feat)

**Plan metadata:** _(docs commit to follow)_

## Files Created/Modified

- `scripts/seed.py` — idempotent seed script; MERGE-based upsert for all 12 node types and all relationships

## Decisions Made

None - followed plan as specified.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. Script reads Neo4j credentials from `.env` via `get_settings()`.

## Next Phase Readiness

- `scripts/seed.py` ready; run `python scripts/migrate.py && python scripts/seed.py` with Neo4j up to populate test data
- Plan 03-02 (queries.py) can now reference candidate c-001 and all its relationships
- Plan 03-03 (eval harness) has a concrete test fixture to evaluate against

---
*Phase: 03-test-data-eval*
*Completed: 2026-05-07*

## Self-Check: PASSED

- FOUND: scripts/seed.py
- FOUND: .planning/phases/03-test-data-eval/03-01-SUMMARY.md
- FOUND: commit cd7627f
