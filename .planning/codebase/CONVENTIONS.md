---
title: CONVENTIONS
description: Code style, naming, patterns, and error handling conventions for HUMAN.AI
last_mapped: 2026-04-30
---

# CONVENTIONS

## Language & Runtime

- **Python 3.11+** — required minimum version
- Type annotations are mandatory; `mypy` runs in strict mode

## Linting & Formatting

Tool: **Ruff** (`ruff>=0.4`)

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]
```

- `E` — pycodestyle errors
- `F` — pyflakes (undefined names, unused imports)
- `I` — isort (import ordering)
- `UP` — pyupgrade (modern Python syntax)

Commands:
```bash
ruff check .        # lint
ruff format .       # format
```

## Type Checking

Tool: **mypy** (`mypy>=1.10`), strict mode

```toml
[tool.mypy]
python_version = "3.11"
strict = true
ignore_missing_imports = true
```

All public functions and methods must have full type annotations. No implicit `Any`.

## Naming Conventions

| Construct | Convention | Example |
|-----------|-----------|---------|
| Modules / packages | `snake_case` | `graph_writer.py` |
| Classes | `PascalCase` | `EntityResolver` |
| Functions / methods | `snake_case` | `resolve_candidate()` |
| Variables | `snake_case` | `extracted_facts` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_MERGE_THRESHOLD` |
| Pydantic models | `PascalCase` | `ExtractedFact`, `RawDocument` |
| Neo4j node labels | `PascalCase` | `Candidate`, `Skill`, `Fact` |
| Neo4j relationship types | `UPPER_SNAKE_CASE` | `HAS_SKILL`, `EXTRACTED_FROM` |
| Qdrant collections | `snake_case` | `skills`, `experiences`, `resumes` |

## Data Validation

**Pydantic v2** is used everywhere for data modeling:
- All API request/response schemas
- LLM extraction output schemas (`ExtractedFact`, structured output)
- Internal data transfer objects (`RawDocument`, `Shortlist`)
- Configuration (`pydantic-settings`)

Validation happens at system boundaries only (API input, LLM output). Internal code trusts typed interfaces.

## Architectural Patterns

### Fact Node Provenance (mandatory)
Every claim about a candidate is stored as a `Fact` node, not as a direct property:

```
Candidate -[:HAS_FACT]-> Fact -[:EXTRACTED_FROM]-> Document
Fact -[:SUPPORTS]-> Skill | Experience | Education
Candidate -[:HAS_SKILL]-> Skill   # denormalized for query speed
```

Do **not** bypass `Fact` node by writing direct relationships without provenance.

### Graph as Source of Truth
Qdrant is an index, not the source of truth. Every Qdrant search result must be resolved back to Neo4j for full context. Never treat a vector search result as final.

### Idempotency
All ingestion operations must be idempotent:
- Use `MERGE` (not `CREATE`) in Cypher for all node/relationship writes
- Use SHA-256 content hash to skip already-ingested documents
- Conflict resolution: new facts marked `is_current: true`, old facts retained (never deleted)

### Async Ingestion
All ingestion steps (parse → extract → resolve → write) run as Celery tasks:
- Each step is a separate, idempotent Celery task
- No in-memory state shared between steps — full state lives in Neo4j
- `POST /documents` returns immediately with `document_id` + `task_id`
- Status polling via `GET /documents/{document_id}`

## Error Handling

- One Neo4j transaction per document — rollback entire document on failure, re-queue for retry
- LLM extraction uses structured output (schema-guided); validate against Pydantic schema before writing to graph
- Entity resolution: automatic merge only on exact match (email, phone, name+DOB); fuzzy match creates `pending_merge` status, requires human confirmation
- Extraction outputs without `fact_id` references in grounded generation are discarded (hallucination guard)

## Project Structure Conventions

```
api/      FastAPI route handlers — thin, delegate to core/
core/     Domain logic — ingestion pipeline, graph ops, retrieval
tests/    pytest test suite mirroring core/ structure
```

- `api/` is thin — no business logic, only HTTP handling and delegation to `core/`
- `core/` contains all domain logic; submodules map to pipeline stages

## Configuration

- All settings via `pydantic-settings` — environment variables or `.env` file
- No hardcoded connection strings, credentials, or model names in source code
- Docker Compose used for all local infra (Neo4j, Qdrant, Redis)
