---
title: STRUCTURE
description: Directory layout, key file locations, and naming conventions for HUMAN.AI
last_mapped: 2026-04-30
---

# STRUCTURE

## Repository Root

```
C:/dev/HUMAN.AI/
├── api/                    # FastAPI app and route handlers
│   └── .gitkeep            # (skeleton — no source files yet)
├── core/                   # Domain logic: ingestion pipeline, graph ops, retrieval
│   └── .gitkeep            # (skeleton — no source files yet)
├── tests/                  # pytest test suite
│   └── (empty)
├── neo4j/                  # Neo4j data/logs (Docker volume mounts)
│   ├── data/
│   └── logs/
├── qdrant_storage/         # Qdrant vector storage (Docker volume mount)
├── storage/                # Local object storage for raw documents (planned)
│   └── documents/
│       └── {document_id}/
│           ├── {original_filename}
│           └── text.txt
├── .planning/              # GSD planning artifacts
│   └── codebase/           # Codebase map documents
├── .claude/                # Claude Code configuration
├── docker-compose.yml      # Infrastructure services (Neo4j, Qdrant, Redis)
├── pyproject.toml          # Python project metadata, dependencies, tool config
├── CLAUDE.md               # Claude Code instructions for this repo
├── core_architecture.md    # Primary architecture reference (Russian)
└── README.md               # Project readme
```

## Key Directories

### `api/` — HTTP Layer
- FastAPI application and route handlers
- Thin layer: no business logic, only HTTP handling
- Planned files:
  - `api/main.py` — FastAPI app instantiation, router registration
  - `api/routes/documents.py` — `POST /documents`, `GET /documents/{id}`
  - `api/routes/search.py` — `POST /search`
  - `api/schemas.py` — Pydantic request/response models

### `core/` — Domain Logic
- All domain logic: ingestion pipeline, graph operations, retrieval
- No HTTP dependencies
- Planned files:
  - `core/parser.py` — PDF/DOCX/Huntflow JSON → `RawDocument`
  - `core/extractor.py` — `RawDocument` → `ExtractedFact[]` via LLM structured output
  - `core/resolver.py` — Entity deduplication and merge logic
  - `core/graph_writer.py` — `ExtractedFact[]` → Neo4j Cypher transactions
  - `core/vector.py` — BGE-M3 embedding + Qdrant upsert/search
  - `core/retrieval.py` — Query Planner, Hybrid Search, Grounded Generation
  - `core/tasks.py` — Celery task definitions
  - `core/models.py` — Shared Pydantic models (`RawDocument`, `ExtractedFact`, `Shortlist`)

### `tests/` — Test Suite
- Mirrors `core/` directory structure
- All tests use pytest with `asyncio_mode = "auto"`
- Planned eval harness lives here for extraction precision/recall measurement

## Infrastructure (Docker Compose)

All infra runs locally via Docker Compose:

| Service | Image | Host Port | Purpose |
|---------|-------|-----------|---------|
| Neo4j | `neo4j:5-community` | `7474` (HTTP), `7687` (Bolt) | Graph database — source of truth |
| Qdrant | `qdrant/qdrant:latest` | `6333` | Vector index |
| Redis | `redis:7-alpine` | `6379` | Celery task broker |

```bash
docker compose up -d    # start all infra services
```

Neo4j auth: `neo4j / ${NEO4J_PASSWORD:-changeme}` (env var or default)

## Object Storage

Raw documents stored on local disk (planned path pattern):
```
./storage/documents/{document_id}/{original_filename}   # raw file
./storage/documents/{document_id}/text.txt              # extracted plain text
```

Migration path to MinIO or S3-compatible object storage is planned but not in MVP scope.

## Configuration & Settings

- `pyproject.toml` — project metadata, dependencies, Ruff/mypy/pytest config
- `.env` (not committed) — secrets and connection strings for local dev
- All settings via `pydantic-settings` (environment variables)

## Naming Conventions

| Artifact | Convention | Example |
|----------|-----------|---------|
| Python source files | `snake_case.py` | `graph_writer.py`, `entity_resolver.py` |
| Test files | `test_{module}.py` | `test_graph_writer.py` |
| Pydantic models | `PascalCase` | `RawDocument`, `ExtractedFact` |
| Neo4j node labels | `PascalCase` | `Candidate`, `Skill`, `Fact` |
| Neo4j relationship types | `UPPER_SNAKE_CASE` | `HAS_SKILL`, `EXTRACTED_FROM` |
| Qdrant collection names | `snake_case` | `skills`, `experiences`, `resumes` |
| Docker volume dirs | `snake_case` | `qdrant_storage`, `neo4j/data` |

## Important Files to Read First

Before making structural decisions, read:
- `CLAUDE.md` — project instructions and architectural rules
- `core_architecture.md` — full architecture reference (Russian); contains graph ontology, component responsibilities, data flows, and open design decisions
- `pyproject.toml` — dependency versions and tooling config
- `docker-compose.yml` — infrastructure service definitions and port bindings

---

*Structure analysis: 2026-04-30 — codebase is pre-implementation (skeleton only)*
