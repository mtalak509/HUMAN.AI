---
status: partial
phase: 03-test-data-eval
source: [03-VERIFICATION.md]
started: 2026-05-07T00:00:00.000Z
updated: 2026-05-07T00:00:00.000Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. SEED-01: seed.py loads candidate without duplicates
expected: `python scripts/seed.py` runs to completion with log "Seed complete: candidate c-001 loaded"; second run produces the same log without errors and without creating new nodes in Neo4j
result: [pending]

### 2. SEED-02: Query functions return correct candidates from seed set
expected: After running seed.py, each of the 3 query functions returns `[{"id": "c-001", "full_name": "Алексей Соколов"}]`:
- `find_candidates_by_skill(driver, "Python")` → `[{"id": "c-001", ...}]`
- `find_candidates_by_company(driver, "TechFlow Analytics")` → `[{"id": "c-001", ...}]`
- `find_candidates_by_status(driver, "v-001", "in_progress")` → `[{"id": "c-001", ...}]`
result: [pending]

### 3. TEST-02: pytest tests/test_infra.py passes with live stack
expected: `docker compose up -d neo4j qdrant redis` running → `pytest tests/test_infra.py` exits 0 with 3 tests green (test_neo4j_ping, test_qdrant_health, test_redis_ping)
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
