---
title: STRUCTURE
description: Directory layout, key file locations, and naming conventions for HUMAN.AI
last_mapped: 2026-05-04
---

# STRUCTURE

## Repository Root

```
C:/dev/HUMAN.AI/
├── api/                    # FastAPI HTTP layer (thin)
│   ├── __init__.py
│   └── main.py             # App, lifespan, /health, DI helpers
├── core/                   # Domain + infrastructure (no FastAPI imports here)
│   ├── __init__.py
│   ├── config.py           # pydantic-settings; get_settings() lru_cache'd
│   ├── logger.py           # Loguru setup_logging
│   ├── database/
│   │   └── graph.py        # GraphDB — async Neo4j driver, retry, degraded mode
│   └── schemas/
│       └── models.py       # Pydantic ontology node models (Candidate, Fact, …)
├── tests/                  # pytest test suite (add as phases land)
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
├── docker-compose.yml      # Neo4j, Qdrant, Redis, FastAPI app service
├── Dockerfile              # API image (uvicorn api.main:app)
├── pyproject.toml          # Python project metadata, dependencies, tool config
├── CLAUDE.md               # Claude Code instructions for this repo
├── core_architecture.md    # Primary architecture reference (Russian)
└── README.md               # Project readme
```

## Key Directories

### `api/` — HTTP layer

- FastAPI application object and routes live here.
- **Imports:** `core.config`, `core.database.graph`, `core.logger` — no business logic duplicated in HTTP handlers long-term.
- **Current:** `api/main.py` — lifespan wiring, `GET /health`, `get_settings` / `get_db` for `Depends`.
- **Planned:** `api/routes/*.py` routers, optional `api/schemas.py` for request/response DTOs distinct from graph ontology models.

### `core/` — domain and side-effecting services

- **No FastAPI** in `core/` — keeps graph, extraction, and retrieval testable without HTTP.
- **Layout:**
  - `core/config.py` — environment-backed `Settings`.
  - `core/logger.py` — structured logging bootstrap.
  - `core/database/graph.py` — Neo4j `GraphDB` (async driver, `connect_with_retry`, `ping`, `session`, `close`).
  - `core/schemas/models.py` — Pydantic models aligned with the graph ontology (import surface for writers/extractors).

- **Still planned** (not necessarily at `core/` root — follow `core_architecture.md` when adding):

  - `core/parser.py` — PDF/DOCX → raw text / structured intake
  - `core/extractor.py` — LLM structured output → facts
  - `core/resolver.py` — entity deduplication / merge
  - `core/graph_writer.py` — validated models → Cypher transactions
  - `core/vector.py` — embeddings + Qdrant
  - `core/retrieval.py` — query planning, hybrid search
  - `core/tasks.py` — Celery tasks

### `tests/` — test suite

- Mirror `core/` (and later `api/`) layout where it helps navigation.
- Pytest: `asyncio_mode = "auto"` (see `pyproject.toml`).

## Infrastructure (Docker Compose)

All infra runs locally via Docker Compose:

| Service | Image / build | Host port | Purpose |
|---------|----------------|-----------|---------|
| Neo4j | `neo4j:5-community` | `7474` (HTTP), `7687` (Bolt) | Graph database — source of truth |
| Qdrant | `qdrant/qdrant:latest` | `6333` | Vector index |
| Redis | `redis:7-alpine` | `6379` | Celery broker |
| FastAPI | `build: .` (Dockerfile) | `8000` | HTTP API (`uvicorn api.main:app`) |

```bash
docker compose up -d    # infra + API (per compose file)
```

Neo4j auth: `neo4j / ${NEO4J_PASSWORD:-changeme}` (env var or default).

## Object Storage

Raw documents stored on local disk (planned path pattern):

```
./storage/documents/{document_id}/{original_filename}   # raw file
./storage/documents/{document_id}/text.txt              # extracted plain text
```

Migration path to MinIO or S3-compatible object storage is planned but not in MVP scope.

## Configuration & Settings

- `pyproject.toml` — project metadata, dependencies, Ruff/mypy/pytest config.
- `.env` (not committed) — secrets and connection strings for local dev.
- All settings via `pydantic-settings` (environment variables).

## Naming Conventions

| Artifact | Convention | Example |
|----------|-----------|---------|
| Python source files | `snake_case.py` | `graph_writer.py`, `entity_resolver.py` |
| Test files | `test_{module}.py` | `test_graph_writer.py` |
| Pydantic models | `PascalCase` | `Candidate`, `Fact` |
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

*Structure map aligned with repo layout as of 2026-05-04.*
