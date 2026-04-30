---
title: CONCERNS
description: Technical debt, known issues, security concerns, and fragile areas for HUMAN.AI
last_mapped: 2026-04-30
---

# CONCERNS

## Security

### Default Neo4j Credentials in docker-compose.yml
**Severity:** High
**Location:** `docker-compose.yml`
```yaml
NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:-changeme}
```
The fallback `changeme` password is used if `NEO4J_PASSWORD` is not set. A developer who forgets to set the env var runs an exposed Neo4j with a known default credential.
**Mitigation:** Remove the default fallback; fail hard if `NEO4J_PASSWORD` is not set. Document required env vars.

### No API Authentication
**Severity:** High
The FastAPI app has no authentication layer yet. `POST /documents` and `POST /search` are open endpoints. The architecture doc explicitly defers RBAC and multi-tenancy.
**Mitigation:** Add at minimum a static bearer token check before first real deployment. Full RBAC is out of scope for MVP.

### Unauthenticated Qdrant and Redis
**Severity:** Medium
Both `qdrant/qdrant:latest` and `redis:7-alpine` are configured without passwords in `docker-compose.yml`. Exposed on `localhost` only — acceptable locally, but risky if the VM's firewall is misconfigured.
**Mitigation:** Bind services to `127.0.0.1` explicitly in docker-compose; add Redis `requirepass` before any cloud deployment.

### Deferred 152-ФЗ PII Compliance
**Severity:** Medium (deferred by design)
Candidate PII (names, contacts, resumes) is stored in Neo4j and object storage with no consent tracking, audit log, or right-to-erasure implementation. Architecture doc explicitly defers this to a pre-enterprise-pilot phase.
**Mitigation:** Design Neo4j schema to support soft-delete and PII purge paths from the start (add `consent_id` to `Candidate`, `deleted_at` flags). Implement erasure before first real client data enters.

## Technical Debt

### No LLM Provider Abstraction
**Severity:** Medium
The architecture doc notes that the LLM provider is "TBD — decided after cost benchmarks." There is currently no abstraction layer (interface / adapter) for the LLM client, meaning provider selection will require touching all call sites.
**Mitigation:** Define a `LLMClient` protocol (structural typing) before writing the first LLM call. Swap implementations without changing extractor/planner logic.

### Local Disk Object Storage with No Abstraction
**Severity:** Low-Medium
Raw documents will be stored at `./storage/documents/{id}/` with hardcoded path construction. The architecture doc notes migration to MinIO/S3 is planned.
**Mitigation:** Introduce a `StorageBackend` abstraction early; local-disk is one implementation. Avoids path logic scattered across parser and writer.

### No Re-extraction Path
**Severity:** Low (deferred by design)
Facts store `model_version` but there is no workflow to re-extract documents when the model or prompt changes. Old facts from prior model versions will coexist indefinitely with new ones.
**Mitigation:** Design the re-extraction trigger as a batch Celery task (re-queue all `Document` nodes where `Fact.model_version != current`). Implement post-pilot.

### Floating Image Tags
**Severity:** Low
`docker-compose.yml` uses `qdrant/qdrant:latest` — this tag will silently pull a new version on `docker compose pull`, potentially breaking vector dimension compatibility.
**Mitigation:** Pin to a specific Qdrant version tag (e.g., `v1.9.x`). Same applies to pinning Neo4j minor version.

## Performance

### BGE-M3 CPU Embeddings — No Batching Strategy Defined
**Severity:** Medium (acceptable for pilot scale)
BGE-M3 runs locally on CPU. For ~300 resumes this is fine (seconds per batch). At 10k+ documents, single-document embedding in Celery tasks will become a bottleneck.
**Mitigation:** Implement batch embedding in the vector layer from day one; Celery tasks should accumulate and embed in configurable batch sizes, not one document at a time.

### 10s Retrieval SLA — No Per-Pass Latency Budget
**Severity:** Low-Medium
The architecture requires `POST /search` to respond within 10 seconds p95. There is no instrumentation or per-pass breakdown (Query Planner / Cypher / Qdrant / Generation) yet.
**Mitigation:** Add per-step timing to retrieval logs from the start; set a Query Planner timeout, a Cypher timeout, and a Qdrant timeout independently.

### Missing Neo4j Index and Constraint Migration Scripts
**Severity:** Medium
The architecture specifies composite keys for `MERGE` idempotency and filtering by skill, status, etc. — but no Cypher migration scripts defining indexes and constraints exist yet.
**Mitigation:** Create a `migrations/` directory with ordered Cypher scripts; run on first startup (or via a simple migration runner in `core/`). Missing indexes will cause full graph scans on every ingestion and retrieval.

## Fragile Areas

### Entity Resolver Auto-Merge — No Undo Mechanism
**Severity:** High
Automatic candidate merges (exact-match on email/phone/name+DOB) are irreversible once committed to Neo4j. A bug in normalization logic (e.g., phone number stripping) could merge two different people.
**Mitigation:** Log every merge decision with the matched fields and values to a dedicated `MergeEvent` node before executing. This creates a recoverable audit trail.

### Qdrant Duplicate Vectors on Re-ingestion
**Severity:** Medium
If a document is re-processed (e.g., after a `failed` status retry), the vector layer may upsert duplicate embeddings for the same entity under a new Qdrant point ID.
**Mitigation:** Use deterministic Qdrant point IDs derived from Neo4j node IDs (e.g., `uuid5(neo4j_skill_id)`). This makes upserts idempotent.

### Celery Worker Failure Handling — Opaque Retry State
**Severity:** Medium
The architecture specifies Neo4j as the state machine for document status, but the interaction between Celery's built-in retry mechanism and the Neo4j `failed` status is not yet specified. A task that has exhausted retries may leave a document stuck in `parsing` status.
**Mitigation:** Define a maximum retry count; on final failure, explicitly set document status to `failed` with an error message in Neo4j.

## Scaling Limits

### Neo4j Community — Single Node, No Backup
**Severity:** Low (acceptable for MVP)
Neo4j Community Edition is single-instance with no built-in backup automation or replication. It is the sole source of truth.
**Mitigation:** Add a scheduled `neo4j-admin dump` to a cron job before any production data enters the system. Document migration path to AuraDB or Neo4j Enterprise.

### No Health Check Endpoints
**Severity:** Low
No `/health` or `/ready` endpoint exists. This makes liveness detection, Docker health checks, and load balancer configuration impossible.
**Mitigation:** Add a trivial `/health` endpoint (checks Neo4j and Qdrant connectivity) before deploying to any non-local environment.

## Missing Infrastructure

| Item | Impact | Priority |
|------|--------|----------|
| DB migration system (Cypher schema migrations) | Schema drift between environments | High |
| Neo4j indexes and constraints | Performance and data integrity | High |
| Health check endpoints (`/health`, `/ready`) | Operability | Medium |
| Structured observability (logs, latency metrics) | Debugging extraction and retrieval quality | Medium |
| Object storage abstraction | Portability from local disk | Low |
| Eval harness implementation | Cannot validate extraction quality | High (for pilot) |

## Test Coverage Gaps

- **Zero source code exists yet** — the codebase is a pre-implementation skeleton; all test coverage is 0%
- Entity resolver has no test fixtures planned for edge cases (multiple candidates with same name, phone number normalization variants)
- Parser cascade (pdfplumber → pypdf → tesseract) has no test corpus of representative Russian-language resumes
- Eval harness (50 resumes + 50 HR notes gold set) is not yet assembled

---

*Concerns analysis: 2026-04-30 — codebase is pre-implementation (skeleton only)*
