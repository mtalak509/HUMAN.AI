# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

HUMAN.AI — Talent Intelligence Platform. Backend that ingests resumes and recruiter notes, stores them as a knowledge graph (Neo4j), indexes them in a vector store (Qdrant), and retrieves ranked candidate shortlists via natural language queries.

Architecture reference: `core_architecture.md` — read it before making structural decisions.

## Stack

- **Python 3.11+**, FastAPI, Pydantic v2
- **Neo4j 5.x** — graph of truth (candidates, skills, experience, facts)
- **Qdrant** — vector index for fuzzy search; always resolved back to Neo4j for full context
- **Celery + Redis** — async ingestion pipeline
- **BGE-M3** — local CPU embeddings (multilingual, computed once)
- **Docker Compose** — all infra services locally

## Project structure

```
api/      FastAPI app and route handlers
core/     Domain logic: ingestion pipeline, graph operations, retrieval
tests/    pytest test suite
```

## Commands

```bash
# Install deps (editable + dev extras)
pip install -e ".[dev]"

# Start infra (Neo4j, Qdrant, Redis)
docker compose up -d

# Run app
uvicorn api.main:app --reload

# Lint
ruff check .
ruff format .

# Type check
mypy .

# Tests
pytest
pytest tests/path/to/test_file.py::test_name   # single test
pytest --cov=. --cov-report=term-missing        # with coverage
```

## Key architectural decisions

**Graph is source of truth; vector store is an index.** Every Qdrant result must be resolved to Neo4j for the full node context. Never treat a vector search result as final.

**Fact node provenance.** Extracted claims are stored as `Fact` nodes linked to their source `Document`, then linked to the canonical entity (Skill, Experience, etc.) and denormalized directly onto the Candidate for query speed. Do not bypass the Fact node pattern.

**Conflict handling.** Conflicting facts are never deleted — the new one is marked `is_current: true` and the old remains in the graph.
