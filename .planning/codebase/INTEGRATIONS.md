# External Integrations

**Analysis Date:** 2026-04-30

## APIs & External Services

**LLM Provider (TBD):**
- Service: External LLM API — provider not yet selected (decision deferred until after Phase 1 extraction quality eval)
- Used for: structured output extraction from resumes/notes, Query Planner (function calling), Grounded Generation
- SDK/Client: `httpx>=0.27` (direct HTTP) or provider SDK — to be determined
- Auth: `LLM_API_KEY` env var

**ATS — Huntflow:**
- Service: Huntflow ATS (primary candidate/vacancy data source for pilot client)
- Used for: pulling candidate profiles, vacancies, pipeline statuses, recruiter notes via Huntflow API
- SDK/Client: `httpx>=0.27` (async HTTP client; no official Python SDK bundled)
- Auth: Huntflow API token (env var not yet defined in `.env.example` — to be added)
- Data mapping: Huntflow JSON fields map directly to `RawDocument` without LLM parsing (per architecture doc section 5.1)

## Data Storage

**Databases:**

- **Neo4j 5.x Community** — graph of truth
  - Docker image: `neo4j:5-community` (defined in `docker-compose.yml`)
  - Ports: `7474` (HTTP browser), `7687` (Bolt protocol)
  - Connection: `NEO4J_URI=bolt://localhost:7687`
  - Credentials: `NEO4J_USER` / `NEO4J_PASSWORD`
  - Client: `neo4j>=5.20` (official Python driver)
  - Data volume: `./neo4j/data` (host-mounted)
  - Logs volume: `./neo4j/logs` (host-mounted)

- **Qdrant** — vector index (not source of truth)
  - Docker image: `qdrant/qdrant:latest` (defined in `docker-compose.yml`)
  - Port: `6333` (REST + gRPC)
  - Connection: `QDRANT_HOST` / `QDRANT_PORT`
  - Client: `qdrant-client>=1.9`
  - Collections (from architecture doc): `skills`, `companies`, `experiences`, `resumes`
  - All payloads reference Neo4j node IDs (e.g., `neo4j_candidate_id`, `neo4j_skill_id`)
  - Data volume: `./qdrant_storage` (host-mounted)

- **Redis 7** — Celery broker and result backend
  - Docker image: `redis:7-alpine` (defined in `docker-compose.yml`)
  - Port: `6379`
  - Connection: `REDIS_URL=redis://localhost:6379/0`
  - Used exclusively as Celery transport; no application-level caching defined yet

**File Storage:**
- Local filesystem at `STORAGE_PATH` (default: `./storage`) for pilot
  - Path convention: `storage/documents/{document_id}/{original_filename}` (source file)
  - Path convention: `storage/documents/{document_id}/text.txt` (extracted text)
- Migration path: MinIO or Selectel S3 when volume exceeds pilot scale (architecturally prepared, no code coupling)

**Caching:**
- None — no application-level cache layer defined. Query Planner caching (for repeated NL queries) is noted as a future latency optimization in architecture doc.

## Authentication & Identity

**Auth Provider:**
- Not implemented — auth/RBAC explicitly out of scope for current iteration (per `core_architecture.md` section 1 and CLAUDE.md)
- No auth middleware in FastAPI skeleton at this stage

## Monitoring & Observability

**Error Tracking:**
- None — no Sentry or equivalent integrated

**Logs:**
- Approach: JSON files during pilot (`LOG_LEVEL` env var; value `info` in example)
- Architecture doc notes: each extractor and retrieval run logs inputs, outputs, model versions, latency, and token counts
- Optional future path: simple Postgres table for structured log storage (deferred, not in MVP)

## CI/CD & Deployment

**Hosting:**
- Single VM, Docker Compose (explicit pilot constraint per `core_architecture.md` section 9)
- No Kubernetes, no managed container service for pilot

**CI Pipeline:**
- Not detected — no `.github/workflows/`, `.gitlab-ci.yml`, or equivalent CI config present

## Environment Configuration

**Required env vars** (from `.env.example`):
- `NEO4J_URI` — Neo4j Bolt connection URI
- `NEO4J_USER` — Neo4j username
- `NEO4J_PASSWORD` — Neo4j password
- `QDRANT_HOST` — Qdrant hostname
- `QDRANT_PORT` — Qdrant port
- `REDIS_URL` — Redis connection URL (Celery broker)
- `LLM_API_KEY` — LLM provider API key (value TBD by provider choice)
- `LLM_MODEL` — LLM model identifier (value TBD)
- `EMBEDDING_DEVICE` — BGE-M3 device (`cpu` for all current targets)
- `STORAGE_PATH` — root path for document file storage
- `DEBUG` — application debug flag
- `LOG_LEVEL` — logging verbosity

**Secrets location:**
- `.env` file at project root (gitignored per `.gitignore`)
- Template: `.env.example` (committed, no secret values)

## Webhooks & Callbacks

**Incoming:**
- None defined yet. Architecture doc describes `GET /documents/{document_id}` for polling ingestion status, and optional WebSocket/SSE for task progress — not yet implemented.

**Outgoing:**
- None.

## Embeddings Service

**BGE-M3 (local, CPU):**
- Package: `FlagEmbedding>=1.2`
- Model: BGE-M3 (multilingual, supports Russian and English)
- Runtime: local CPU — no external API call, no network dependency for embeddings
- Computed once per document at ingestion; incremental updates only
- Controlled via `EMBEDDING_DEVICE` env var

---

*Integration audit: 2026-04-30*
