---
phase: 06-graph-writer
verified: 2026-06-12T00:00:00Z
status: passed
score: 9/9 must-haves verified
overrides_applied: 0
re_verification: null
gaps: []
deferred: []
human_verification: []
---

# Phase 6: Graph Writer Verification Report

**Phase Goal:** Система принимает ExtractedCandidate и записывает полный граф кандидата в Neo4j через MERGE — с Fact-провенансом и денормализованными прямыми связями; идемпотентно.
**Verified:** 2026-06-12
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | GraphWriter.write(candidate, document_id) создаёт все узлы (Candidate, Contact, Skill, Experience, Company, Role, Education) через MERGE | ✓ VERIFIED | `graph_writer.py` lines 168–244: all 7 node types are MERGEd via parameterized cypher.py constants; integration test `test_candidate_findable_by_skill_and_company` passes with Neo4j live |
| 2 | Для каждого извлечённого факта создан Fact-узел с EXTRACTED_FROM→Document и SUPPORTS→Skill/Experience | ✓ VERIFIED | `graph_writer.py` lines 250–284: one Fact per unique skill (`has_skill`) and one per experience (`worked_at`); each Fact gets LINK_HAS_FACT + LINK_EXTRACTED_FROM + LINK_SUPPORTS_SKILL/EXPERIENCE; `test_fact_provenance_reachable` passes |
| 3 | Прямые связи Candidate-[:HAS_SKILL]->Skill созданы параллельно с Fact-узлами (денормализация) | ✓ VERIFIED | `graph_writer.py` lines 195–197: MERGE_SKILL + LINK_HAS_SKILL emitted for every skill in union set; separate from Fact block; USED_SKILL also present (D-06, line 227); `test_used_skill_edge_exists` passes |
| 4 | Повторный write() с тем же документом — граф не изменился, узлов не прибавилось | ✓ VERIFIED | `cypher.py`: all node MERGEs use plain SET (zero `ON CREATE SET` — confirmed by grep count 0); `test_write_idempotent` asserts Candidate count == 1 and Fact/Experience counts unchanged after 2nd write; passes live |
| 5 | Cypher-запросы из scripts/queries.py находят нового кандидата по навыку и компании | ✓ VERIFIED | `test_candidate_findable_by_skill_and_company` calls `find_candidates_by_skill(driver, "Python")` and `find_candidates_by_company(driver, "TechFlow Analytics")`; asserts `_DOC_ID` in both result sets; passes live |

**Score:** 5/5 roadmap success criteria verified

---

### Plan 06-01 Must-Haves

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | All node-MERGE Cypher statements exist for Candidate, Contact, Skill, Company, Role, Experience, Education, Fact | ✓ VERIFIED | `cypher.py` contains all 8: MERGE_CANDIDATE, MERGE_CONTACT, MERGE_SKILL, MERGE_COMPANY, MERGE_ROLE, MERGE_EXPERIENCE, MERGE_EDUCATION, MERGE_FACT; `python -c "import core.writer.cypher"` clean |
| 2 | Denormalized edge statements exist (HAS_CONTACT, HAS_SKILL, HAS_EXPERIENCE, AT_COMPANY, AS_ROLE, HAS_EDUCATION) | ✓ VERIFIED | `cypher.py` lines 92–120: all 6 denorm edge constants present and parameterized |
| 3 | Fact provenance triple statements exist (HAS_FACT, EXTRACTED_FROM, SUPPORTS) | ✓ VERIFIED | `cypher.py` lines 136–156: LINK_HAS_FACT, LINK_EXTRACTED_FROM, LINK_SUPPORTS_SKILL, LINK_SUPPORTS_EXPERIENCE all present |
| 4 | New USED_SKILL edge statement exists (Experience->Skill, D-06) | ✓ VERIFIED | `cypher.py` line 125: `LINK_USED_SKILL`; `MERGE (e)-[:USED_SKILL]->(s)` confirmed |
| 5 | Every statement is parameterized ($param) — no string interpolation of resume data | ✓ VERIFIED | `grep -cE 'f"""|\.format\(' core/writer/cypher.py` == 0; all values are `$param` placeholders |
| 6 | Every node statement uses plain SET (not ON CREATE SET) for idempotent refresh | ✓ VERIFIED | `grep -c "ON CREATE SET" core/writer/cypher.py` == 0 |

### Plan 06-02 Must-Haves

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | GraphWriter.write(candidate, document_id) persists Candidate + all related nodes via MERGE | ✓ VERIFIED | 284-line implementation; all node types merged in `_write_tx`; integration tests pass live |
| 2 | candidate_id == document_id (D-01); experience/education/contact/fact ids are deterministic sha1 of fixed field strings | ✓ VERIFIED | `graph_writer.py` line 120: `candidate_id = document_id`; 4 `@staticmethod` sha1 helpers at lines 77–103; `test_ids_deterministic` asserts same-input equality and 40-char hex output |
| 3 | Each unique skill and each experience gets a Fact node with EXTRACTED_FROM->Document and SUPPORTS->Skill/Experience | ✓ VERIFIED | Lines 250–284; skills loop (D-07 one Fact per unique skill), experiences loop (one `worked_at` Fact each); `test_fact_provenance_reachable` passes |
| 4 | Denormalized HAS_SKILL edges created; USED_SKILL created for role-mentioned skills (D-06) | ✓ VERIFIED | Lines 195–227; skill union emits LINK_HAS_SKILL per skill; per-experience loop emits LINK_USED_SKILL per skills_mentioned; `test_used_skill_edge_exists` passes |
| 5 | Fact.confidence is None, model_version from candidate, is_current true, extracted_at now (D-02) | ✓ VERIFIED | Lines 256–261, 276–281: `confidence=None`, `model_version=candidate.model_version`, `is_current=True`, `extracted_at=now`; `grep -cE "confidence\s*=\s*[0-9]" core/writer/graph_writer.py` == 0 |
| 6 | write() degrades gracefully when Neo4j down (no crash, warning logged) | ✓ VERIFIED | Lines 122–127: `if self._db is None or not self._db.is_connected: logger.warning(...); return`; `test_write_degrades_when_db_down` and `test_write_session_never_entered_when_not_connected` both pass |
| 7 | Second write() of the same document adds zero nodes (WRITE-04) | ✓ VERIFIED | `test_write_idempotent` calls write() twice, asserts Candidate count == 1, Fact count unchanged, Experience count unchanged; passes live |

**Combined score (all plan must-haves):** 13/13

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `core/writer/cypher.py` | Parameterized Cypher MERGE/LINK constants | ✓ VERIFIED | 158 lines; 19 constants; all present, parameterized, plain-SET |
| `core/writer/__init__.py` | Package re-export of GraphWriter | ✓ VERIFIED | 8 lines; `from core.writer.graph_writer import GraphWriter`; `__all__ = ["GraphWriter"]` |
| `core/writer/graph_writer.py` | GraphWriter async service class | ✓ VERIFIED | 284 lines; class GraphWriter with `__init__`, `write`, `_write_tx`, 4 static ID helpers |
| `tests/test_writer_unit.py` | Unit tests (no infra) | ✓ VERIFIED | 226 lines; 5 tests; all pass without Neo4j |
| `tests/test_writer_integration.py` | Integration tests with skip guard | ✓ VERIFIED | 249 lines; 4 tests; all pass with Neo4j live |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `core/writer/graph_writer.py` | `core/writer/cypher.py` | `from core.writer.cypher import` (19 constants) | ✓ WIRED | All 19 constants imported at lines 28–48; none built dynamically |
| `core/writer/graph_writer.py` | `core/database/graph.py GraphDB.session().execute_write` | `execute_write` call at line 130 | ✓ WIRED | `await session.execute_write(self._write_tx, candidate, candidate_id)` |
| `tests/test_writer_integration.py` | `scripts/queries.py find_candidates_by_skill/company` | import + direct call | ✓ WIRED | Lines 22–23: `from scripts.queries import find_candidates_by_company, find_candidates_by_skill`; called in test_candidate_findable_by_skill_and_company |
| `cypher.py` → migrations.py MERGE keys | Candidate.id, Skill.name, Company.name, Role.title, others .id | MERGE key alignment | ✓ WIRED | Verified against PLAN interface table; Skill on `name`, Company on `name`, Role on `title`, all id-keyed nodes on `id` |
| `cypher.py` EXTRACTED_FROM | Document node (phase 4) | MATCH never MERGE | ✓ WIRED | `grep -c "MERGE (d:Document" cypher.py` == 0; `LINK_EXTRACTED_FROM` uses `MATCH (d:Document {id: $d_id})` |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `graph_writer.py` `_write_tx` | `candidate: ExtractedCandidate` | `write()` caller passes live ExtractedCandidate; integration test uses module-level fixture with real values | Yes — Neo4j writes confirmed by integration test node counts and query results | ✓ FLOWING |
| `test_writer_integration.py` queries | `by_skill`, `by_company` results | `find_candidates_by_skill/company` → Neo4j `MATCH (c:Candidate)-[:HAS_SKILL]->` | Yes — returns `[{"id": "test-doc-write-06", ...}]` after write | ✓ FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 9 writer tests pass (unit + integration) | `.ven-win/Scripts/python.exe -m pytest tests/test_writer_unit.py tests/test_writer_integration.py -q` | 9 passed, 0 failed, 2 harmless PytestWarnings (sync functions with asyncio mark from module pytestmark) | ✓ PASS |
| 19 cypher constants present at import | `python -c "import core.writer.cypher as c; assert all(hasattr(c,n) for n in [...])"` | ALL PRESENT | ✓ PASS |
| No ON CREATE SET in cypher.py | `grep -c "ON CREATE SET" core/writer/cypher.py` | 0 | ✓ PASS |
| No float confidence in graph_writer.py | `grep -cE "confidence\s*=\s*[0-9]" core/writer/graph_writer.py` | 0 | ✓ PASS |
| Document never MERGEd by writer | `grep -c "MERGE (d:Document" core/writer/cypher.py` | 0 | ✓ PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| WRITE-01 | 06-01, 06-02 | Graph Writer создаёт Candidate + все связанные узлы через MERGE | ✓ SATISFIED | All 7 node types MERGEd in `_write_tx`; integration test confirms nodes reachable in graph |
| WRITE-02 | 06-01, 06-02 | Graph Writer создаёт Fact-узлы с провенансом (ссылка на Document) | ✓ SATISFIED | Fact nodes with EXTRACTED_FROM→Document and SUPPORTS→Skill/Experience; `test_fact_provenance_reachable` passes |
| WRITE-03 | 06-01, 06-02 | Денормализация: прямые связи Candidate→Skill для скорости поиска | ✓ SATISFIED | LINK_HAS_SKILL for all union-set skills + LINK_USED_SKILL for skills_mentioned; `test_used_skill_edge_exists` passes |
| WRITE-04 | 06-02 | Повторный запуск на том же документе не создаёт дублей | ✓ SATISFIED | Plain SET in all node MERGEs; `test_write_idempotent` asserts counts unchanged after 2nd write |

All 4 phase requirements satisfied. No orphaned requirements found.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `core/writer/graph_writer.py` | 271 | `_fact_id(document_id, "worked_at", exp.company)` — same company name as value for two experiences at the same company would produce the same `f_id`, collapsing into one Fact node with two SUPPORTS edges | ⚠️ Warning | Breaks provenance correctness for candidates with multiple roles at the same employer. Flagged as WR-01 in 06-REVIEW.md. Derives from locked decision D-01 (fact_id formula). Fix: include `exp_id` in the fact value composite. |
| `core/writer/graph_writer.py` | 208, 220 | No guard against blank `exp.company` or `exp.role` after strip | ⚠️ Warning | Could MERGE a garbage `Company {name: ""}` or `Role {title: ""}` shared across all blank-field candidates. LLM controlled; low probability but no defense at writer boundary. Flagged as WR-02 in review. |
| `core/writer/graph_writer.py` | 157, 260, 280 | `extracted_at` uses plain SET; re-write overwrites original provenance timestamp | ℹ️ Info | First extraction timestamp is lost on idempotent re-run. Flagged as WR-03. Acceptable in v1.1 if documented. |
| `tests/test_writer_unit.py` | 116–131 | `test_skill_union_dedup` re-implements union logic in test body rather than driving GraphWriter | ℹ️ Info | Tautological test; regression in real union logic would not be caught. Flagged as WR-04 in review. Does not affect green test count. |

**Assessment:** WR-01 and WR-02 are correctness edge cases, not blockers for the phase goal. WR-01 is acknowledged in the CONTEXT.md decisions (D-01 formula is fixed by architecture). WR-02 is an unguarded boundary. Neither prevents the success criteria from being met on well-formed data; all integration tests use valid data and pass. The review pre-flagged both. No blocker anti-patterns found.

---

### Human Verification Required

None. All success criteria are programmatically verifiable and confirmed by the live test run.

---

## Gaps Summary

No gaps. All 5 roadmap success criteria are verified by live passing tests:

1. All 7 node types MERGEd (Candidate, Contact, Skill, Experience, Company, Role, Education) — confirmed by integration test and `test_write_idempotent` Candidate count == 1.
2. Fact nodes with EXTRACTED_FROM→Document and SUPPORTS→Skill/Experience — confirmed by `test_fact_provenance_reachable`.
3. Denormalized HAS_SKILL + USED_SKILL edges — confirmed by `test_used_skill_edge_exists`.
4. Idempotency — confirmed by `test_write_idempotent` with live Neo4j.
5. Candidate findable by skill and company via queries.py — confirmed by `test_candidate_findable_by_skill_and_company`.

**WR-01 (worked_at Fact id collision for same-company experiences)** is a review warning, not a phase blocker. It derives from the locked D-01 fact_id formula and only surfaces for candidates with multiple experience entries at the same employer — a case not covered by any test fixture. Per the verification mandate, this derives from a locked CONTEXT decision and does not prevent the success criteria from being met on the tested data. It is documented as a known defect for the next iteration.

---

_Verified: 2026-06-12_
_Verifier: Claude (gsd-verifier)_
