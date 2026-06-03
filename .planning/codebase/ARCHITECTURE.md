<!-- refreshed: 2026-04-30 -->
# Architecture

**Analysis Date:** 2026-04-30

## System Overview

```text
┌──────────────────────────────────────────────────────────────────────┐
│                        Sources                                        │
│   Huntflow API / PDF / DOCX files / HR notes                         │
└─────────────────────────────┬────────────────────────────────────────┘
                              │  POST /documents
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      FastAPI Layer  (`api/`)                          │
│   Route handlers — accept uploads, return task_id, expose /search    │
└──────────────┬───────────────────────────────────────────────────────┘
               │  Celery task enqueue (Redis broker)
               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   Async Ingestion Pipeline  (`core/`)                 │
│                                                                        │
│  Parser → LLM Extractor → Entity Resolver → Graph Writer             │
│   PDF/DOCX/JSON         structured output   dedup/merge   Cypher tx  │
└──────────────┬────────────────────────────────────────┬──────────────┘
               │ MERGE nodes / HAS_FACT edges            │ upsert vectors
               ▼                                         ▼
┌──────────────────────────┐              ┌──────────────────────────┐
│   Neo4j 5.x  (graph)     │◄─────────────│   Qdrant  (vector index) │
│   Source of truth        │  hop for ctx │   skills / companies /   │
│   `bolt://localhost:7687`│              │   experiences / resumes  │
└──────────────────────────┘              └──────────────────────────┘
               ▲                                         ▲
               │                                         │
┌──────────────────────────────────────────────────────────────────────┐
│                    KAG Retrieval Pipeline  (`core/`)                  │
│                                                                        │
│  Query Planner → Hybrid Search → Grounded Generation                 │
│  (LLM function   Cypher hard +   LLM + fact_id                       │
│   calling)       Qdrant soft     citations                            │
└──────────────────────────────────────────────────────────────────────┘
               │
               ▼
         Shortlist with provenance-cited reasoning
```

## Component Responsibilities

| Component | Responsibility | Planned location |
|-----------|----------------|-----------------|
| FastAPI app | HTTP entry points, async task dispatch, /search endpoint | `api/main.py` |
| Parser | Raw document → `RawDocument` (text + metadata). PDF cascade + OCR | `core/parser.py` |
| LLM Extractor | `RawDocument` → `ExtractedFact[]` via structured output | `core/extractor.py` |
| Entity Resolver | Dedup / merge candidates, skills, companies against graph | `core/resolver.py` |
| Graph Writer | `ExtractedFact[]` → Cypher transactions (MERGE, idempotent) | `core/graph_writer.py` |
| Vector Layer | Embed and upsert to Qdrant; resolve search hits back to Neo4j | `core/vector.py` |
| KAG Retrieval | Query Planner + Hybrid Search + Grounded Generation | `core/retrieval.py` |
| Celery workers | Async ingestion orchestration over Redis | `core/tasks.py` |

## Pattern Overview

**Overall:** Knowledge-Augmented Generation (KAG) over a provenance graph

**Key Characteristics:**
- Graph (Neo4j) is the single source of truth; Qdrant is an index, never a source
- Every extracted claim lives as a `Fact` node linked to its source `Document` before being denormalized onto the `Candidate` for query speed
- All ingestion steps are idempotent — safe to retry; document SHA-256 hash guards against re-ingestion
- Conflicting facts are never deleted; the newer one receives `is_current: true`
- All retrieval answers must cite `fact_id` per claim — uncited claims are discarded

## Layers

**API Layer:**
- Purpose: HTTP surface, async task dispatch, response shaping
- Location: `api/`
- Contains: FastAPI route handlers, Pydantic request/response models
- Depends on: `core/` domain logic, Celery task queue
- Used by: External clients (recruiters, Huntflow webhook)

**Core — Ingestion Pipeline:**
- Purpose: Transform raw documents into graph-resident knowledge
- Location: `core/`
- Contains: Parser, LLM Extractor, Entity Resolver, Graph Writer, Celery tasks
- Depends on: Neo4j driver, Qdrant client, LLM API, BGE-M3 embedder, object storage
- Used by: API layer (via Celery), direct invocation in tests

**Core — Retrieval Pipeline:**
- Purpose: Answer NL queries with a grounded, cited shortlist
- Location: `core/`
- Contains: Query Planner, Hybrid Search, Grounded Generation
- Depends on: Neo4j (Cypher), Qdrant (pre-filtered vector search), LLM API
- Used by: `POST /search` API endpoint

**Infrastructure Services:**
- Purpose: Persistent storage and task brokering
- Services: Neo4j 5 Community (`bolt://localhost:7687`), Qdrant (`localhost:6333`), Redis 7 (`localhost:6379`)
- Defined in: `docker-compose.yml`

## Data Flow

### Ingestion Path

1. Client uploads document — `POST /documents` (`api/` route handler)
2. Route handler stores raw file to `./storage/documents/{document_id}/` and creates a `Document` node in Neo4j with status `queued`
3. Celery task enqueued on Redis broker
4. **Parser** extracts plain text (pdfplumber → pypdf → tesseract OCR → python-docx cascade); produces `RawDocument`
5. **LLM Extractor** sends `RawDocument` text + ontology context to LLM (structured output); receives `ExtractedFact[]`
6. **Entity Resolver** deduplicates candidates (email / phone / name+DOB exact match; fuzzy → `pending_merge`), skills and companies (canonical_name exact → Qdrant cosine similarity)
7. **Graph Writer** executes a single Neo4j transaction: `MERGE` nodes, create `Fact` nodes with `EXTRACTED_FROM → Document` and `SUPPORTS → Skill|Experience|…`, denormalize direct `HAS_SKILL` / `HAS_EXPERIENCE` edges onto `Candidate`
8. Qdrant upsert: embed skill names, company names, experience text, resume text; store `neo4j_*_id` in payload
9. Document node status updated to `written` (or `failed` on exception — entire transaction rolled back, task retried)

### Retrieval Path (POST /search)

1. NL query received at `POST /search` (`api/` route handler)
2. **Query Planner** (LLM function calling): parses query into hard filters (`filter_by_skill`, `filter_by_experience`, `filter_by_status`, …) and soft criteria (`semantic_match`)
3. **Hard search**: Cypher query built from hard filters → candidate set from Neo4j
4. **Soft search** (if candidate set is large or no hard filters): embed soft criteria → Qdrant search with `candidate_id IN [...]` pre-filter → intersect with candidate set
5. **Ranking**: weighted score combining graph relevance + vector similarity + recency
6. **Grounded Generation**: for top-N candidates, assemble enriched context from Neo4j (Experience, Skills, Facts with sources); LLM generates reasoning with mandatory `fact_id` citations; post-processor discards uncited claims
7. Return `Shortlist[Candidate, score, reasoning_with_citations[]]`

**State Management:**
- All pipeline state persisted in Neo4j (document status, fact versions, merge flags)
- No in-memory state between ingestion steps — each step reads from and writes to Neo4j
- This enables Celery → Airflow migration without changing step logic

## Key Abstractions

**RawDocument:**
- Purpose: Normalised output of the Parser — plain text + source metadata
- Pattern: Pydantic v2 model; language/format-agnostic contract between Parser and Extractor

**ExtractedFact:**
- Purpose: One atomic claim produced by the LLM Extractor
- Properties: `predicate`, `value`, `confidence`, `model_version`, `extracted_at`
- Pattern: Pydantic v2 model; maps 1-to-1 to a `Fact` node in Neo4j

**Fact node (Neo4j):**
- Purpose: Provenance carrier — every piece of knowledge is traceable to its source document
- Relationships: `Candidate -[:HAS_FACT]-> Fact -[:EXTRACTED_FROM]-> Document`, `Fact -[:SUPPORTS]-> Skill|Experience|Education|…`
- Constraint: Never deleted; conflicts resolved by `is_current` flag

**Qdrant Collections:**
- `skills` — skill name embeddings; payload: `neo4j_skill_id`, `canonical_name`
- `companies` — company name embeddings; payload: `neo4j_company_id`, `canonical_name`
- `experiences` — experience period text embeddings; payload: `neo4j_experience_id`, `candidate_id`, `from`, `to`
- `resumes` — full resume text embeddings; payload: `neo4j_candidate_id`

**Extraction Schema (Pydantic):**
- Purpose: JSON Schema contract passed to LLM for structured output
- Covers: candidate basics (name, contacts), Experience list, Education list, Skill list, salary/role preferences
- Separate narrower schema for HR notes (status, rejection_reason, salary_expectation, soft_signal)

## Entry Points

**HTTP API:**
- Location: `api/main.py` (planned)
- Triggers: HTTP requests from recruiter clients / Huntflow webhooks
- Key routes:
  - `POST /documents` — upload document, returns `document_id` + `task_id`
  - `GET /documents/{document_id}` — poll ingestion status (`queued` | `parsing` | `extracting` | `resolving` | `written` | `failed`)
  - `POST /search` — synchronous NL search, 10 s timeout, returns shortlist

**Celery Worker:**
- Location: `core/tasks.py` (planned)
- Triggers: Tasks enqueued by API on Redis
- Runs: parse → extract → resolve → write pipeline steps

**CLI / Direct Invocation:**
- Location: `core/` modules
- Triggers: pytest test suite, eval harness, manual backfill scripts

## Architectural Constraints

- **Threading:** FastAPI async (asyncio event loop); Celery workers are separate processes — no shared memory
- **Global state:** BGE-M3 embedding model loaded once per worker process (CPU inference); Neo4j and Qdrant clients are module-level singletons
- **Idempotency hard requirement:** every ingestion step must be safe to re-run; SHA-256 content hash guards document re-ingestion; Neo4j `MERGE` by composite key guards node duplication
- **Merge safety:** Automatic candidate merge only on exact match (email, phone, name+DOB). Fuzzy matches create `pending_merge` status — never auto-merge
- **Fact immutability:** Existing `Fact` nodes are never updated or deleted; conflict resolution sets `is_current: true` on the new fact only
- **Retrieval timeout:** `POST /search` must complete within 10 seconds p95

## Anti-Patterns

### Treating Qdrant as source of truth

**What happens:** Using a Qdrant search result directly as the final answer without hopping to Neo4j
**Why it's wrong:** Qdrant payload contains only IDs and minimal metadata — full context (Experience, Facts, provenance) lives in Neo4j only
**Do this instead:** Every Qdrant result must be resolved to Neo4j via `neo4j_*_id` payload field before being returned to the caller

### Bypassing the Fact node

**What happens:** Writing `Candidate -[:HAS_SKILL]-> Skill` directly without creating a `Fact` node
**Why it's wrong:** Destroys provenance — there is no way to trace the claim to its source document, version, or confidence score
**Do this instead:** Always create `Fact` → link `Fact -[:EXTRACTED_FROM]-> Document` and `Fact -[:SUPPORTS]-> Skill` → then also write the denormalized `Candidate -[:HAS_SKILL]-> Skill` for query speed

### Deleting conflicting facts

**What happens:** Overwriting or removing an old `Fact` node when a newer extraction contradicts it
**Why it's wrong:** Eliminates the audit trail and prevents debugging extraction quality over model versions
**Do this instead:** Mark the new fact `is_current: true`; leave the old fact intact

### Returning LLM output without citation validation

**What happens:** Passing grounded generation text to the caller without verifying every claim has a `fact_id`
**Why it's wrong:** Enables hallucination — the LLM may fabricate statements not backed by graph data
**Do this instead:** Post-process all generation output; discard any sentence/claim that lacks a valid `fact_id` reference

## Error Handling

**Strategy:** Fail-fast per pipeline stage; full Neo4j transaction rollback on any step failure; document status set to `failed`; Celery auto-retry with backoff

**Patterns:**
- Document node status machine (`queued` → `parsing` → `extracting` → `resolving` → `written` | `failed`) persisted in Neo4j — survives worker restarts
- Extraction failures logged with document_id, model_version, and error; surfaced via `GET /documents/{id}`
- Entity Resolver fuzzy-match uncertainty creates `pending_merge` status rather than raising — the pipeline continues without blocking

## Cross-Cutting Concerns

**Logging:** Structured JSON logs per pipeline step — inputs, outputs, model versions, latency, token counts; written to files on MVP (Postgres table planned post-pilot)
**Validation:** Pydantic v2 throughout — from LLM extraction schema to API request/response contracts
**Provenance:** Every Neo4j node and edge traceable to a `Document` via `Fact` chain; every retrieval answer must cite `fact_id` per claim
**Embeddings:** BGE-M3 (FlagEmbedding) computed locally on CPU; embedded once at ingestion time, never recomputed unless re-extraction is explicitly triggered

---

*Architecture analysis: 2026-04-30*
