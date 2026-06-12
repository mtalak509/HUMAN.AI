# Phase 6: Graph Writer - Pattern Map

**Mapped:** 2026-06-12
**Files analyzed:** 5 new (3 src + 2 test)
**Analogs found:** 5 / 5 (every file has a strong in-repo analog)

## File Classification

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `core/writer/__init__.py` | package re-export | — | `core/extractor/__init__.py` | exact |
| `core/writer/cypher.py` | constants/query library | transform (data→Cypher) | `scripts/seed.py` (MERGE bodies) + `core/parser/pdf.py` (`MERGE_DOCUMENT_CYPHER` module const) | exact (statements) / role-match (placement) |
| `core/writer/graph_writer.py` | service (writer) | CRUD (graph write) + event-driven (called by Celery task, phase 7) | `core/parser/pdf.py::PdfParser` (degradation + idempotent MERGE) + `core/extractor/llm.py::Extractor` (async class, Settings/DI) + `scripts/seed.py::_seed_candidate` (the actual MERGE sequence) | exact (composed of 3 analogs) |
| `tests/test_writer_unit.py` | test | — | `tests/test_extractor_unit.py` | exact |
| `tests/test_writer_integration.py` | test | — | `tests/test_parser_integration.py` | exact |

**Note on D-06 (`USED_SKILL` edge):** this is the ONE pattern with NO analog — it is a brand-new relationship type absent from `seed.py` and the ontology. See "No Analog Found".

---

## Pattern Assignments

### `core/writer/__init__.py` (package re-export)

**Analog:** `core/extractor/__init__.py` (lines 1-9)

Copy the module-docstring + explicit re-export + `__all__` shape exactly. The writer's public surface is the `GraphWriter` class (no `ExtractedCandidate` re-export needed — it lives in `core.extractor`).

```python
"""core.writer — Graph Writer layer.

Public API re-exported here.
"""

from core.writer.graph_writer import GraphWriter

__all__ = ["GraphWriter"]
```

---

### `core/writer/cypher.py` (Cypher statement library)

**Analog A — module-level Cypher constant placement:** `core/parser/pdf.py` lines 27-39 (`MERGE_DOCUMENT_CYPHER`). Note the in-code comments that pin the contract: *"bound parameters, no string interpolation"*, *"MERGE on .id only … do not change the key"*, *"Uses SET (not ON-CREATE-SET) — re-parsing refreshes fields idempotently (WRITE-04)"*. Replicate this comment discipline per statement.

**Analog B — the actual MERGE bodies to port:** `scripts/seed.py`. Port each statement, swapping hardcoded kwargs for `$param` placeholders. The seed file is the canonical reference for every node + denorm edge + Fact triple.

**CRITICAL DEVIATION from seed.py — use `SET`, not `ON CREATE SET / ON MATCH SET`.**
`seed.py` uses the verbose `ON CREATE SET … ON MATCH SET …` form. The writer must follow the parser's idempotency decision (CONTEXT D-08, specifics line 102-103): plain `SET` so a re-`write()` of the same document REFRESHES the node. So `MERGE_DOCUMENT_CYPHER` (parser) is the structural template, `seed.py` is the field/edge inventory.

**Node MERGE — id-keyed (Candidate / Experience / Education / Contact / Fact):** seed.py lines 28-35 (Candidate), 92-99 (Experience), 115-127 (Education), 177-189 (Fact). Rewrite as:
```python
MERGE_CANDIDATE = """
MERGE (n:Candidate {id: $id})
SET n.full_name = $full_name, n.status = $status
RETURN n
"""
```

**Node MERGE — natural-key (Skill `name` / Company `name` / Role `title`):** seed.py lines 50-54 (Skill, key `name`, no other props), 58-64 (Company), 75-81 (Role). MERGE key MUST match `core/database/migrations.py` constraints (`skill_name_unique`, `company_name_unique`, `role_title_unique`) — see "Shared Patterns → MERGE keys". Skill carries only `name` (D-05: no canonicalization, store verbatim):
```python
MERGE_SKILL = "MERGE (n:Skill {name: $name})"
```

**Fact node (D-02 fields):** seed.py lines 177-189 is the shape, but the writer sets `confidence = null` (D-02 — do NOT copy seed's `0.95`/`1.0`), `model_version = candidate.model_version`, `is_current = true`, plus `extracted_at = now()` (seed omits `extracted_at`; the ontology `Fact.extracted_at` and `fact_is_current_idx`/`fact_predicate_idx` indexes exist — populate `predicate`, `is_current`, `extracted_at`):
```python
MERGE_FACT = """
MERGE (n:Fact {id: $id})
SET n.predicate = $predicate, n.value = $value,
    n.confidence = $confidence, n.model_version = $model_version,
    n.is_current = $is_current, n.extracted_at = $extracted_at
RETURN n
"""
```

**Denormalized edge MERGE (MATCH→MATCH→MERGE):** seed.py is exhaustive here — copy verbatim, parameterize keys:
- `HAS_CONTACT` lines 213-218 · `HAS_SKILL` lines 221-227 · `HAS_EXPERIENCE` lines 230-235 · `AT_COMPANY` lines 236-241 · `AS_ROLE` lines 242-247 · `HAS_EDUCATION` lines 270-275.
```python
LINK_HAS_SKILL = (
    "MATCH (c:Candidate {id: $c_id}) MATCH (s:Skill {name: $name}) "
    "MERGE (c)-[:HAS_SKILL]->(s)"
)
```

**Fact provenance triple (HAS_FACT / EXTRACTED_FROM / SUPPORTS):** seed.py lines 308-325 (skill Fact) and 327-345 (experience Fact) is the exact template. `EXTRACTED_FROM` targets the Document already created by the parser (phase 4) — MATCH it by `document_id`, never MERGE/re-create it (CONTEXT line 25, 163-164):
```python
LINK_HAS_FACT = (
    "MATCH (c:Candidate {id: $c_id}) MATCH (f:Fact {id: $f_id}) "
    "MERGE (c)-[:HAS_FACT]->(f)"
)
LINK_EXTRACTED_FROM = (
    "MATCH (f:Fact {id: $f_id}) MATCH (d:Document {id: $d_id}) "
    "MERGE (f)-[:EXTRACTED_FROM]->(d)"
)
LINK_SUPPORTS_SKILL = (
    "MATCH (f:Fact {id: $f_id}) MATCH (s:Skill {name: $name}) "
    "MERGE (f)-[:SUPPORTS]->(s)"
)
```

**`USED_SKILL` (D-06) — NEW, no seed analog.** Structurally identical to `LINK_HAS_SKILL` but `Experience`→`Skill`:
```python
LINK_USED_SKILL = (
    "MATCH (e:Experience {id: $e_id}) MATCH (s:Skill {name: $name}) "
    "MERGE (e)-[:USED_SKILL]->(s)"
)
```

---

### `core/writer/graph_writer.py` (GraphWriter service)

Composed from THREE analogs. Each contributes a distinct slice.

**Slice 1 — class shape, constructor, Settings/DI (from `core/extractor/llm.py::Extractor`, lines 70-110):**
Constructor takes injected dependencies, not FastAPI `Depends`. The writer is called from a Celery task (phase 7) so it must accept a `GraphDB` in its constructor (CONTEXT line 157-158), mirroring `PdfParser(db=...)` (pdf.py lines 71-79) rather than `Extractor(settings=...)`. Recommended signature:
```python
class GraphWriter:
    def __init__(self, db: GraphDB | None = None, settings: Settings | None = None) -> None:
        self._db = db
        self._settings = settings or get_settings()
```

**Slice 2 — graceful degradation guard (from `core/parser/pdf.py`, lines 160-177):**
Guard on `is_connected` BEFORE `session()` (session() raises `RuntimeError` when disconnected — graph.py lines 82-83). On outage: log warning, return without crashing. This is the load-bearing pattern.
```python
if self._db is None or not self._db.is_connected:
    logger.warning("graph_writer: Neo4j unavailable — candidate graph not persisted id={}", candidate_id)
    return  # or a result object — no crash (CONTEXT specifics line 101-102)
```

**Slice 3 — async + single write transaction (from CONTEXT D-discretion lines 86-88 + graph.py `session()`):**
`write()` is `async`. Per CONTEXT discretion, wrap the whole candidate graph in ONE `session.execute_write(tx_fn)` transaction for atomicity (no half-written graph). `execute_write` takes a callback that receives a transaction and runs all the `tx.run(...)` calls. (Note: `seed.py` uses sequential `session.run(...)` with no single-transaction wrapper — that is the one place to IMPROVE on the seed analog, per D-discretion.)
```python
async def write(self, candidate: ExtractedCandidate, document_id: str) -> None:
    candidate_id = document_id  # D-01: candidate_id = document_id
    if self._db is None or not self._db.is_connected:
        logger.warning(...); return
    async with self._db.session() as session:
        await session.execute_write(self._write_tx, candidate, candidate_id)
```

**Slice 4 — deterministic ID derivation (D-01, NO analog for the hashing itself — closest is pdf.py `_compute_document_id` lines 81-88 using `hashlib`):**
Static helpers mirroring `PdfParser._compute_document_id`'s `@staticmethod` + `hashlib` style. D-01 fixes the field concatenation; hash fn (sha1/sha256) and separator are discretion:
```python
@staticmethod
def _experience_id(document_id: str, company: str, role: str, from_date: str) -> str:
    raw = f"{document_id}|{company}|{role}|{from_date}"
    return hashlib.sha1(raw.encode()).hexdigest()
# similarly: _education_id (doc|institution|from_date), _contact_id (doc|type|value),
#            _fact_id (doc|predicate|value)
```

**Slice 5 — skill union + dedup (D-04/D-05, business logic, no analog):**
```python
skills = {s.strip() for s in candidate.skills}
for exp in candidate.experiences:
    skills |= {s.strip() for s in exp.skills_mentioned}
# D-05: only .strip() + exact-string dedup; NO lowercasing / canonicalization
```

**Slice 6 — provenance stamping discipline (echo of `Extractor._validate`, llm.py lines 146-161):**
`Fact.model_version` comes from `candidate.model_version` (already stamped by the extractor), `confidence=None` (D-02), `is_current=True`, `extracted_at=now()`. Use `dt.datetime.now(dt.UTC).isoformat()` exactly as pdf.py line 175.

---

### `tests/test_writer_unit.py` (no infra, mocked DB)

**Analog:** `tests/test_extractor_unit.py` (entire file).

Copy:
- Module docstring listing numbered behaviours (lines 1-13).
- `pytestmark = pytest.mark.asyncio(loop_scope="session")` (line 26) — REQUIRED per CLAUDE.md asyncio fixture rule.
- Mock pattern: build a `MagicMock` session/db, inject via attribute (`writer._db = mock_db`), assert on `.call_args_list` / `.call_count` (lines 84-87, 114-131).

Writer-specific unit tests to author:
- `write()` with `db=None` or `is_connected=False` → returns, no crash, no `session()` call (mirror the degradation test pattern; assert warning logged, `session` never entered).
- Deterministic ID helpers: same inputs → same hash; different inputs → different hash.
- Skill union: top-level `skills` ∪ `experiences[*].skills_mentioned`, deduped after `.strip()` (D-04/D-05).
- One `has_skill` Fact per UNIQUE skill (D-07) — assert no duplicate Fact ids.

**SimpleNamespace mock-response trick** (lines 57-61) is OpenAI-specific — NOT needed here; instead mock the Neo4j `session`/`tx` and assert the Cypher + params passed to `.run()`.

### `tests/test_writer_integration.py` (skips cleanly when Neo4j down)

**Analog:** `tests/test_parser_integration.py` (entire file).

Copy verbatim:
- `pytestmark = pytest.mark.asyncio(loop_scope="session")` (line 17).
- The `graph_db: GraphDB` fixture usage + `if not graph_db.is_connected: pytest.skip("Neo4j unavailable")` guard at the top of EVERY infra test (lines 20-22, 36-38, 62-64).
- Idempotency assertion shape (lines 36-59): write twice, then `MATCH (...) RETURN count(...) AS c` and assert `c == 1` (WRITE-04). Apply to Candidate, each Skill, each Experience, each Fact.

Writer-specific integration tests:
- After `write()`, the candidate is findable by `scripts/queries.py::find_candidates_by_skill/company` (success criterion #5, CONTEXT lines 133-134, 164-165).
- Fact provenance reachable: `MATCH (c:Candidate)-[:HAS_FACT]->(f:Fact)-[:EXTRACTED_FROM]->(d:Document)` and `(f)-[:SUPPORTS]->(:Skill|:Experience)`.
- `USED_SKILL` edge exists for a skill that appeared in a role's `skills_mentioned`.

---

## Shared Patterns

### MERGE keys MUST match constraints (source of truth)
**Source:** `core/database/migrations.py` lines 9-71 (CONSTRAINTS).
**Apply to:** every node MERGE in `cypher.py`.

| Node | MERGE key | Constraint |
|------|-----------|------------|
| Candidate | `id` | `candidate_id_unique` |
| Contact | `id` | `contact_id_unique` |
| Skill | `name` | `skill_name_unique` |
| Role | `title` | `role_title_unique` |
| Company | `name` | `company_name_unique` |
| Experience | `id` | `experience_id_unique` |
| Education | `id` | `education_id_unique` |
| Fact | `id` | `fact_id_unique` |

Never MERGE on a different field (CLAUDE.md "MERGE keys match constraints"). Skill/Company/Role have NO synthetic id (D-01).

### Index-backed fields — populate them
**Source:** `core/database/migrations.py` lines 76-98 (INDEXES).
**Apply to:** Fact and Experience writes. The writer must set the fields the indexes are built on: `Fact.is_current` (`fact_is_current_idx`), `Fact.predicate` (`fact_predicate_idx`), `Experience.is_current` (`experience_is_current_idx`), `Candidate.full_name` (`candidate_full_name_idx`). `Experience.is_current` is available directly from `ExtractedCandidate` (schema.py `is_current` computed_field, lines 43-47).

### Graceful degradation guard
**Source:** `core/parser/pdf.py` lines 160-164 + `core/database/graph.py` lines 82-83.
**Apply to:** `GraphWriter.write()`. Guard `self._db is None or not self._db.is_connected` BEFORE `session()`. A Neo4j outage must never crash the writer (CONTEXT specifics line 101-102; CLAUDE.md "GraphDB graceful degradation").

### Idempotent MERGE via `SET` (not `ON CREATE SET`)
**Source:** `core/parser/pdf.py` lines 28-39 (`MERGE_DOCUMENT_CYPHER`).
**Apply to:** every node MERGE. `SET` (not `ON CREATE SET / ON MATCH SET`) so a re-`write()` refreshes the node — satisfies WRITE-04 / D-08. This OVERRIDES the `ON CREATE/ON MATCH` style seen in `seed.py`.

### Async sync-offload (if any sync work appears)
**Source:** `core/parser/pdf.py` lines 121-126 / `core/extractor/llm.py` lines 183-185 (`run_in_executor`).
**Apply to:** the writer only IF a synchronous step is introduced. The Neo4j async driver is already non-blocking, so `write()` awaits `session.execute_write` directly — `run_in_executor` is likely NOT needed (unlike parser/extractor whose pypdf/OpenAI calls are sync). Note for the planner: do not add `run_in_executor` around async driver calls.

### Provenance stamped by caller, never invented
**Source:** `core/extractor/llm.py` lines 146-161.
**Apply to:** Fact writes. `Fact.model_version = candidate.model_version`; `Fact.confidence = None` (D-02 — do NOT invent a constant like seed's 0.95).

### asyncio session-loop test marker
**Source:** `tests/test_parser_integration.py` line 17, `tests/test_extractor_unit.py` line 26.
**Apply to:** both writer test modules. `pytestmark = pytest.mark.asyncio(loop_scope="session")` — mandatory when using session-scoped `graph_db` driver fixture (CLAUDE.md asyncio rule).

---

## No Analog Found

| Item | Role | Reason | Planner guidance |
|------|------|--------|------------------|
| `USED_SKILL` edge (D-06) | relationship type | New edge type; absent from `seed.py` and the ontology. Edges need no constraint (D-06). | Model structurally on `HAS_SKILL` (seed.py 221-227) but `Experience`→`Skill`. |
| Deterministic composite-ID hashing (D-01) | utility | `pdf.py` hashes raw bytes; here we hash a `|`-joined field string. | Use `hashlib` (`@staticmethod`, pdf.py 81-88 style); concat order is FIXED by D-01, hash fn is discretion. |
| Skill union + strip/dedup (D-04/D-05) | business logic | Pure data-shaping; no graph analog. | Set comprehension; `.strip()` only, no canonicalization (deferred v1.2). |
| Single-transaction wrap `execute_write` | transaction boundary | `seed.py` runs sequential `session.run` with NO single-tx wrapper. | Per CONTEXT D-discretion, IMPROVE on seed: wrap all node+edge writes in one `session.execute_write(tx_fn)` for atomicity. This is a Neo4j-driver API; consult Context7 (neo4j-python-driver) for the `execute_write` callback signature if unsure. |

---

## Metadata

**Analog search scope:** `core/writer/` (target), `scripts/seed.py`, `core/parser/`, `core/extractor/`, `core/database/`, `core/schemas/models.py`, `tests/`
**Files scanned:** 9 read in full + 1 grep (models.py)
**Pattern extraction date:** 2026-06-12
