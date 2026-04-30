---
title: TESTING
description: Test framework, structure, patterns, and coverage for HUMAN.AI
last_mapped: 2026-04-30
---

# TESTING

## Framework

**pytest** (`pytest>=8.2`) with plugins:
- `pytest-asyncio>=0.23` — async test support
- `pytest-cov>=5.0` — coverage reporting

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

`asyncio_mode = "auto"` means all `async def test_*` functions are automatically treated as async tests — no `@pytest.mark.asyncio` decorator needed.

## Running Tests

```bash
pytest                                              # all tests
pytest tests/path/to/test_file.py::test_name        # single test
pytest --cov=. --cov-report=term-missing            # with coverage
```

## Directory Structure

```
tests/
```

Currently empty (codebase is pre-implementation skeleton). Structure should mirror `core/`:

```
tests/
  test_parser/
    test_pdf_parser.py
    test_docx_parser.py
  test_extractor/
    test_llm_extractor.py
    test_extraction_schema.py
  test_resolver/
    test_entity_resolver.py
    test_candidate_merge.py
  test_graph/
    test_graph_writer.py
    test_cypher_queries.py
  test_retrieval/
    test_query_planner.py
    test_hybrid_search.py
    test_grounded_generation.py
  test_api/
    test_documents_endpoint.py
    test_search_endpoint.py
```

## Key Testing Concerns

### Eval Harness (planned)
A dedicated eval harness is part of the architecture — not just unit tests:
- **Gold set:** 50 resumes + 50 HR notes, manually labeled in the extraction schema
- **Metrics per entity type:** precision / recall for `Skill`, `Experience`, `Education`, `Contact`
- **Triggered on:** every prompt or model change in the extractor
- Results written to file / simple dashboard

### Entity Resolver Tests
- Exact match cases: email, phone, name+DOB
- Fuzzy match cases: must create `pending_merge` status, never auto-merge
- False-merge rate target: < 1% on 300 candidates

### Retrieval Eval
- Historical closed vacancies as test fixtures
- Metric: recall@10 — does the actually-hired candidate appear in top-10?
- Compare KAG vs pure vector baseline

### Idempotency Tests
- Re-ingesting same document (same SHA-256 hash) must not create duplicate nodes
- Re-running graph writer on same facts must produce same graph state (Cypher MERGE behavior)

### Provenance Tests
- Every written `Skill`/`Experience` node must be traceable to a `Fact` node
- Every `Fact` must link to a `Document`
- Grounded generation output: all claims must have valid `fact_id` references

## Mocking Strategy

- **Neo4j:** use a real Neo4j instance (test container or dedicated test database) — do not mock the driver; graph query behavior must be verified against real Cypher
- **Qdrant:** real Qdrant instance for integration tests; mock only for pure unit tests on business logic
- **LLM calls:** mock in unit tests; real calls in eval harness only
- **Celery:** `CELERY_TASK_ALWAYS_EAGER = True` for synchronous task execution in tests

## Coverage

Target: measure coverage via `pytest --cov=. --cov-report=term-missing`.

Priority coverage areas:
1. `core/` — all domain logic (extraction, resolution, graph writing, retrieval)
2. Provenance invariants — every node write has fact linkage
3. Idempotency paths — duplicate ingestion, conflict handling
