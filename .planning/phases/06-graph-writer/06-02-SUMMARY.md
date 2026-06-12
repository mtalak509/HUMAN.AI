---
phase: 06-graph-writer
plan: 02
subsystem: database
tags: [neo4j, graph-writer, fact-provenance, idempotency, unit-tests, integration-tests]

# Dependency graph
requires:
  - phase: 06-01
    provides: core/writer/cypher.py (19 Cypher constants — all imports sourced here)
  - phase: 05-extractor
    provides: ExtractedCandidate schema (document_id, model_version, skills, experiences)
  - phase: 04-parser
    provides: Document node in Neo4j (EXTRACTED_FROM targets it by document_id)
  - phase: infra
    provides: GraphDB, migrations constraints (MERGE-key source of truth)

provides:
  - core/writer/graph_writer.py — GraphWriter async service (WRITE-01…WRITE-04 satisfied)
  - tests/test_writer_unit.py — 5 unit tests, no infra, mocked Neo4j
  - tests/test_writer_integration.py — 4 integration tests (pass with Neo4j, skip without)

affects: [07-celery-pipeline, tests-writer]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "GraphWriter DI constructor: db=None safe (mirrors PdfParser), no FastAPI Depends"
    - "execute_write async callback: _write_tx(self, tx, candidate, candidate_id)"
    - "sha1 ID derivation: document_id|field1|field2 separator pattern (D-01)"
    - "Skill union: {s.strip() for s in top_skills} | {s.strip() for s in exp.skills_mentioned}"
    - "Document stub in integration tests: MERGE minimal Document before writer so EXTRACTED_FROM resolves"

key-files:
  created:
    - core/writer/graph_writer.py
    - tests/test_writer_unit.py
    - tests/test_writer_integration.py
  modified: []

key-decisions:
  - "candidate_id = document_id (D-01) — no entity resolver in v1.1"
  - "Fact.confidence = None (D-02) — never invented; grep confirms no float literal"
  - "One Fact per unique skill across the union set (D-07), not per HAS_SKILL/USED_SKILL edge"
  - "Integration tests MERGE a minimal Document stub for EXTRACTED_FROM — parser owns Document creation in production"
  - "_write_tx is an instance method (not staticmethod) — needed to call self._experience_id etc. and self._fact_id from within the transaction callback"

# Metrics
duration: 8min
completed: 2026-06-12
---

# Phase 6 Plan 02: GraphWriter Service Summary

**GraphWriter async class turning ExtractedCandidate into a full Neo4j candidate graph in one execute_write transaction — sha1 D-01 IDs, skill union+strip-only dedup, Fact provenance with confidence=None, USED_SKILL edge, is_connected graceful degradation; 5 unit tests + 4 integration tests green**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-06-12T18:36:14Z
- **Completed:** 2026-06-12T18:43:59Z
- **Tasks:** 3
- **Files created:** 3

## Accomplishments

- Created `core/writer/graph_writer.py` — 284-line async service class with:
  - 4 `@staticmethod` sha1 ID helpers (_experience_id, _education_id, _contact_id, _fact_id) following D-01 formulas
  - `write()` entry point with is_connected + db=None guard (graceful degradation per T-06-07)
  - `_write_tx()` async execute_write callback: all 19 cypher.py constants, correct node+edge sequence mirroring seed.py
  - Skill union set (D-04/D-05): top-level ∪ skills_mentioned, `.strip()` only, no lowercase
  - Fact provenance: one `has_skill` Fact per unique skill (D-07), one `worked_at` Fact per experience (D-03)
  - `confidence=None` enforced (D-02) — grep confirms zero float literals
  - USED_SKILL edges for skills_mentioned per role (D-06)
- Created `tests/test_writer_unit.py` — 5 tests, no infra required:
  - test_ids_deterministic, test_skill_union_dedup, test_write_degrades_when_db_down,
    test_write_session_never_entered_when_not_connected, test_one_fact_per_unique_skill
- Created `tests/test_writer_integration.py` — 4 tests, skip cleanly without Neo4j:
  - test_candidate_findable_by_skill_and_company (success criterion #5 via queries.py)
  - test_fact_provenance_reachable (T-06-06 triple: HAS_FACT→EXTRACTED_FROM→Document)
  - test_used_skill_edge_exists (D-06 USED_SKILL edge)
  - test_write_idempotent (WRITE-04: 2nd write leaves all counts unchanged)

## Task Commits

1. **Task 1: Implement GraphWriter** — `d999234` (feat)
2. **Task 2: Unit tests** — `9f821a3` (test)
3. **Task 3: Integration tests** — `89b5311` (test)

## Files Created

- `core/writer/graph_writer.py` — GraphWriter async service (284 lines)
- `tests/test_writer_unit.py` — 5 unit tests, mocked Neo4j, no infra
- `tests/test_writer_integration.py` — 4 integration tests, skip-on-no-Neo4j

## Decisions Made

- `_write_tx` is an instance method (not a standalone function) so it can call `self._experience_id`, `self._fact_id`, etc. within the transaction callback passed to `execute_write`. The neo4j driver invokes it as `await fn(tx, candidate, candidate_id)` which works correctly because `self` is captured by the bound method.
- Integration tests MERGE a minimal `Document {id, type}` stub in `_ensure_document_stub()` before each write — in production the parser owns Document creation; the stub enables `EXTRACTED_FROM` links to resolve without a real PDF.
- Fixed document_id `"test-doc-write-06"` used in integration tests to keep reruns idempotent.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all data flows wire correctly; no hardcoded empty values or placeholder text.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes beyond what the plan's threat model (T-06-04…T-06-07) already covers.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| core/writer/graph_writer.py | FOUND |
| tests/test_writer_unit.py | FOUND |
| tests/test_writer_integration.py | FOUND |
| .planning/phases/06-graph-writer/06-02-SUMMARY.md | FOUND |
| commit d999234 | FOUND |
| commit 9f821a3 | FOUND |
| commit 89b5311 | FOUND |
