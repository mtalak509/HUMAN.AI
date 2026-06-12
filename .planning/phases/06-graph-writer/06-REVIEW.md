---
phase: 06-graph-writer
reviewed: 2026-06-12T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - core/writer/__init__.py
  - core/writer/cypher.py
  - core/writer/graph_writer.py
  - tests/test_writer_unit.py
  - tests/test_writer_integration.py
findings:
  critical: 0
  warning: 4
  warning_resolved: 3
  warning_open: 1
  info: 3
  total: 7
status: issues_found
resolved:
  - WR-01
  - WR-02
  - WR-04
---

# Phase 6: Code Review Report

**Reviewed:** 2026-06-12
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

The Graph Writer is well structured and disciplined: all Cypher is parameterized
(no resume-derived string interpolation — T-06-01 satisfied), MERGE keys match the
constraints in `core/database/migrations.py`, `Fact.confidence` is correctly forced
to `None` (D-02), all IDs are deterministic (D-01), the `is_connected` guard provides
graceful degradation (T-06-07), and the whole candidate is written in a single
`execute_write` transaction. No injection, secret, or authentication defects were found.

The defects below are correctness/provenance issues, not security holes. The most
important is a `worked_at` Fact id collision when a candidate has two experiences at
the same company (WR-01), which corrupts the SUPPORTS provenance edge — exactly the
kind of multi-experience case the union/Fact logic is supposed to handle. The unit
tests do not exercise multi-experience or empty-string inputs, so these escape the
suite.

## Warnings

### WR-01: `worked_at` Fact id collides across two experiences at the same company  — ✅ RESOLVED 2026-06-12

**Resolution:** `worked_at` Fact id now keyed on `exp_id` (company|role|from_date) via
`_fact_id(document_id, "worked_at", exp_id)`; `Fact.value` stays the readable company
name. Experiences are derived once into a shared `processed_exps` list so the experience
loop and the worked_at loop use identical ids. Regression test
`test_worked_at_fact_no_collision_same_company` asserts two distinct Fact ids + two
distinct SUPPORTS edges for two roles at one company.

**File:** `core/writer/graph_writer.py:267-284`
**Issue:** `_fact_id(document_id, "worked_at", exp.company)` keys the Fact only on
company name, while `_experience_id` keys on `company|role|from_date`. If a candidate
has two experience entries at the same company (re-hire, promotion, or two roles at
one employer — all common on resumes and permitted by the schema), both iterations
produce the **same** `f_id`. The single shared Fact node gets its `value` /
`extracted_at` overwritten by the second pass, and then **two** distinct
`SUPPORTS→Experience` edges are MERGEd from that one Fact (to two different exp_ids).
The result is one `worked_at` Fact that supports two experiences with non-deterministic
property values — broken provenance. (Symmetric note: `_experience_id` is correctly
role+date scoped, so the Experience nodes themselves are fine; only the Fact key is
too coarse.)
**Fix:** Key the `worked_at` Fact on the same composite identity as the experience it
supports, e.g. include the exp_id (or company|role|from_date) in the fact id:
```python
exp_id = self._experience_id(document_id, exp.company, exp.role, exp.from_date)
f_id = self._fact_id(document_id, "worked_at", exp_id)  # 1 Fact per experience
```
Add a unit test with two experiences at the same company asserting two distinct
`worked_at` Fact ids and one SUPPORTS edge each.

### WR-02: Empty-string natural keys create garbage nodes  — ✅ RESOLVED 2026-06-12 (experiences)

**Resolution:** Experiences whose `company` or `role` is blank after `.strip()` are now
skipped in the `processed_exps` build step (logged warning), so no `Company`/`Role`/
`Experience` nodes keyed on `""` are created and no orphan `worked_at` Fact is emitted.
Regression test `test_blank_company_experience_skipped`. NOTE: `edu.institution` blank-guard
was NOT added — education has no blank guard yet (left open, low priority).

**File:** `core/writer/graph_writer.py:208-209, 220-221, 233-237`
**Issue:** `exp.company`, `exp.role`, and `edu.institution` are typed `str` with no
`min_length` in `core/extractor/schema.py`, so the LLM (untrusted input boundary) can
emit `""`. The writer then runs `MERGE (n:Company {name: ""})`, `MERGE (n:Role {title: ""})`,
`MERGE (n:Education {... institution: ""})` plus their edges, polluting the graph with a
single shared empty-named node that every blank experience/role/company across all
candidates collapses onto. Skills already guard against this via `skills.discard("")`
and the `if s:` check at line 226, but company/role/institution have no such guard.
**Fix:** Skip experiences/education whose required natural keys are blank after strip,
or validate non-empty at the boundary:
```python
for exp in candidate.experiences:
    company = exp.company.strip()
    role = exp.role.strip()
    if not company or not role:
        logger.warning("graph_writer: skipping experience with blank company/role")
        continue
```

### WR-03: Re-write mutates `extracted_at` on every run — provenance timestamp is not stable

**File:** `core/writer/graph_writer.py:157, 260, 280`
**Issue:** `MERGE_FACT` uses plain `SET n.extracted_at = $extracted_at` with
`now = dt.datetime.now(...)` recomputed each call. A second `write()` of the same
document (the explicitly supported idempotent re-run, D-08/WRITE-04) overwrites the
original extraction timestamp with a later one. The idempotency tests
(`test_writer_integration.py:180-249`) only assert node *counts*, so this property
drift is invisible. For a provenance/audit field, the first-seen time is usually the
meaningful one.
**Fix:** Use `ON CREATE SET n.extracted_at = $extracted_at` for the timestamp while
keeping plain `SET` for mutable fields (predicate/value/model_version/is_current), or
document explicitly that `extracted_at` means "last write time" not "first extraction
time."

### WR-04: Unit suite re-implements the union logic instead of asserting the writer's output  — ✅ RESOLVED 2026-06-12

**Resolution:** `test_skill_union_dedup` is now async and drives the real `GraphWriter`
via `_build_mock_db_with_capturing_tx`, asserting on the `name=` arguments actually
passed to `MERGE_SKILL` (union, strip-collapse, case preserved, no dup/empty). The
duplicated union logic in the test body was removed — a regression in the writer's
union now fails this test.

**File:** `tests/test_writer_unit.py:116-137`
**Issue:** `test_skill_union_dedup` copy-pastes the union/strip/discard logic from
`graph_writer.py` into the test body and asserts on that local copy — it never calls
`GraphWriter`. If the writer's real union logic regresses, this test still passes
because it tests its own duplicated implementation, not production code. This is a
tautological test that gives false confidence.
**Fix:** Drive the real writer with the capturing-tx mock (already built in
`_build_mock_db_with_capturing_tx`) and assert on the `MERGE_SKILL` `name=` arguments
actually passed to `tx.run`.

## Info

### IN-01: `value` mismatch between `worked_at` Fact and its supported Experience

**File:** `core/writer/graph_writer.py:275`
**Issue:** The `worked_at` Fact stores `value=exp.company` (company name) but
`SUPPORTS` an Experience node identified by company+role+from_date. A consumer reading
`Fact.value` cannot distinguish which of several same-company experiences is meant
without traversing the SUPPORTS edge. Tightly related to WR-01; resolving WR-01's id
scheme makes the relationship unambiguous.
**Fix:** Consider a richer `value` (e.g. `f"{exp.role} @ {exp.company}"`) once WR-01 is
addressed, or document that `value` is intentionally company-only.

### IN-02: Unit-test loop-scope marker plus redundant per-function `@pytest.mark.asyncio`

**File:** `tests/test_writer_unit.py:24, 145, 153, 196`
**Issue:** Module sets `pytestmark = pytest.mark.asyncio(loop_scope="session")` and
then individual async tests also carry `@pytest.mark.asyncio`. The unit tests use no
session-scoped fixtures (db is fully mocked), so the `loop_scope="session"` marker —
copied from the integration pattern in CLAUDE.md — is unnecessary here and the
per-function decorators are redundant with the module-level mark.
**Fix:** Drop the redundant decorators; the module `pytestmark` already marks every
test. Session loop scope is only needed where a session-scoped async fixture (e.g.
`neo4j_driver`) is used, which these unit tests do not use.

### IN-03: `tx` parameter is untyped

**File:** `core/writer/graph_writer.py:140`
**Issue:** `_write_tx(self, tx, ...)` annotates `tx` only via a trailing comment
(`# neo4j.AsyncManagedTransaction`). The project runs `mypy .` (per CLAUDE.md); an
untyped parameter weakens type checking on every `tx.run` call in the hottest method.
**Fix:** Import and annotate: `from neo4j import AsyncManagedTransaction` and
`tx: AsyncManagedTransaction`.

---

_Reviewed: 2026-06-12_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
