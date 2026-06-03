# Technology Stack

**Analysis Date:** 2026-04-30

## Languages

**Primary:**
- Python 3.11+ — all application code (API, core domain logic, ingestion pipeline, tests)

**Secondary:**
- None — single-language backend; no frontend in scope for current iteration

## Runtime

**Environment:**
- Python 3.11+ (minimum version enforced in `pyproject.toml` via `requires-python = ">=3.11"`)

**Package Manager:**
- pip (editable install: `pip install -e ".[dev]"`)
- Lockfile: not present (no `requirements.lock` or `uv.lock`); `pyproject.toml` uses `>=` version bounds

## Frameworks

**Core:**
- FastAPI `>=0.115` — async HTTP API server, OpenAPI generation, Pydantic-native request/response models
- Uvicorn `>=0.30` (with `[standard]` extras: httptools, uvloop, websockets) — ASGI server

**Data Validation:**
- Pydantic `>=2.7` — all data models: extraction schemas, API contracts, settings
- pydantic-settings `>=2.3` — environment-based configuration (`BaseSettings`)

**Task Queue:**
- Celery `>=5.4` (with `[redis]` extra) — async ingestion pipeline (parse → extract → resolve → write)

**Testing:**
- pytest `>=8.2` — test runner
- pytest-asyncio `>=0.23` — async test support (`asyncio_mode = "auto"` in config)
- pytest-cov `>=5.0` — coverage reporting

**Build/Dev:**
- ruff `>=0.4` — linting and formatting (line-length 100, Python 3.11 target, rules: E, F, I, UP)
- mypy `>=1.10` — strict static type checking (`strict = true`, `ignore_missing_imports = true`)

## Key Dependencies

**Critical:**
- `neo4j>=5.20` — official Python driver for Neo4j 5.x; used for all graph reads and writes via Cypher
- `qdrant-client>=1.9` — Python client for Qdrant vector store; used for embedding upserts and ANN search
- `celery[redis]>=5.4` — task queue backed by Redis; all ingestion operations run asynchronously through Celery workers
- `FlagEmbedding>=1.2` — BGE-M3 model loader; produces multilingual embeddings locally on CPU; no external API dependency

**Document Parsing:**
- `pdfplumber>=0.11` — primary PDF text extractor (handles columns, tables)
- `pypdf>=4.2` — fallback PDF extractor (simpler, more tolerant)
- `python-docx>=1.1` — DOCX parsing
- OCR via `tesseract` / `pytesseract` (listed in architecture doc as cascade step 3 for image-only PDFs; not yet in `pyproject.toml` dependencies — to be added)

**HTTP Client:**
- `httpx>=0.27` — async HTTP client; used for external API calls (Huntflow ATS integration)

## Configuration

**Environment:**
- Configured via `.env` file (`.env.example` present at project root with all required keys)
- pydantic-settings reads env vars at startup
- Key configs required (from `.env.example`):
  - `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`
  - `QDRANT_HOST`, `QDRANT_PORT`
  - `REDIS_URL`
  - `LLM_API_KEY`, `LLM_MODEL` (provider TBD — decision deferred to post-Phase 1 eval)
  - `EMBEDDING_DEVICE` (default: `cpu`)
  - `STORAGE_PATH` (default: `./storage` for dev; S3 URI for prod)
  - `DEBUG`, `LOG_LEVEL`

**Build:**
- `pyproject.toml` — single source of project metadata, dependencies, tool configs (ruff, mypy, pytest)
- No separate `setup.py` or `setup.cfg`

## Platform Requirements

**Development:**
- Python 3.11+
- Docker & Docker Compose — required to run infra services (Neo4j, Qdrant, Redis)
- Tesseract OCR (system dependency, not in pyproject.toml) — needed for scanned PDF fallback
- CPU only for embeddings (BGE-M3); no GPU required

**Production:**
- Single VM with Docker Compose (explicit design constraint for pilot phase)
- Target pilot scale: ~300 resumes, 1 recruiter, 1 client
- Logging: JSON files (Postgres optional, deferred)
- Object storage: local disk (`./storage`) for dev/pilot → MinIO or S3 when volume grows

---

*Stack analysis: 2026-04-30*
