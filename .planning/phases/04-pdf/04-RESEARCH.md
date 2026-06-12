# Phase 4: PDF-парсер — Research

**Researched:** 2026-06-03
**Domain:** PDF text extraction, local object storage, Neo4j Document node creation
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Извлечение текста / каскад**
- D-01: v1 использует **только pypdf**. Каскад на pdfplumber **откладывается**.
- D-02: Заложить **чистый шов (seam)** для backend'а извлечения — абстракция/стратегия, чтобы pdfplumber (или другой extractor) вставился позже без переписывания `PdfParser`. Шов обязателен, реализация фолбэка — нет.
- D-03: Успех критерий #4 трактовать как «текст извлечён pypdf, пустых страниц в логах нет»; собственно каскад — отдельная будущая работа.

**Формат сохранённого текста**
- D-04: Извлечённый текст сохраняется в формате **`.md`** (не `.txt`).
- D-05: **Page-маркеры сохраняются** — стиль `--- PAGE i ---` как в `rnd/src/pdf_parser.py`.
- D-06: `text_uri` на Document-узле указывает на `.md`-файл.

**Обработка пустого извлечения**
- D-07: При пустом извлечении — **не падать**. Сохранить исходный PDF, создать Document-узел, текст пустой.
- D-08: На Document пишется флаг **`extraction_status`** (`ok` / `empty`).

**Document-модель**
- D-09: Pydantic-модель `core/schemas/models.py::Document` расширяется новыми полями: `text_uri`, `parser_version`, `extraction_status`.

### Claude's Discretion
- `document_id = SHA-256(pdf_bytes)` — детерминированный id даёт идемпотентность через `MERGE (d:Document {id})`.
- Storage-раскладка внутри `/storage/documents/{document_id}/` (имена файлов, сохранение исходного имени) и формат URI.
- Sync vs async интерфейс `PdfParser.parse()`.
- Точный синтаксис page-маркера (дефолт: сохранить `--- PAGE i ---`).

### Deferred Ideas (OUT OF SCOPE)
- pdfplumber-фолбэк (каскад извлечения) — реализация отложена (D-01).
- OCR для скан-PDF (PARSE-05) — вне v1.1.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PARSE-01 | Система принимает PDF-файл и извлекает plain text | pypdf `PdfReader.pages[i].extract_text()`, extraction-backend Protocol seam |
| PARSE-02 | Система сохраняет исходный PDF и текст на диск (`/storage/documents/{document_id}/`) | SHA-256 as document_id, atomic write pattern, storage layout |
| PARSE-03 | Система создаёт `Document`-узел в Neo4j (file_uri, text_uri, parser_version, ingested_at) | MERGE on Document.id, GraphDB.session() async pattern, extended Pydantic model |
</phase_requirements>

---

## Summary

Phase 4 builds `core/parser/` — a self-contained module that: (1) hashes the PDF bytes to derive a deterministic `document_id`, (2) extracts text page-by-page with pypdf emitting `--- PAGE i ---` markers, (3) saves original PDF and `.md` text file under `/storage/documents/{document_id}/`, and (4) MERGEs a `Document` node into Neo4j. The code is entirely new; there is no pre-existing `core/parser/` directory. `rnd/src/pdf_parser.py::pdf_to_text()` is the battle-tested extraction logic to port in.

The key design decision is the extraction-backend seam: a minimal Python `Protocol` makes `PdfParser` injected-backend-agnostic so pdfplumber, OCR, or any future extractor drops in without changing the public API. The `PdfParser.parse()` method must be async because it calls `GraphDB.session()` (which is `async`), though the pypdf extraction itself is sync CPU-bound work and should be wrapped with `asyncio.get_event_loop().run_in_executor` to avoid blocking the event loop.

**Primary recommendation:** Define a `TextExtractorBackend` Protocol with `extract(pdf_path: Path) -> tuple[str, str]` (text, status). Ship one concrete implementation `PyPdfBackend`. Wire `PdfParser.__init__` to accept an optional `backend` parameter defaulting to `PyPdfBackend()`. Run pypdf IO in a thread executor. MERGE `Document` using the existing `GraphDB.session()` async context manager.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| PDF text extraction | `core/parser/` module | — | CPU-bound library call, no HTTP |
| SHA-256 content hashing | `core/parser/` module | — | Pure bytes computation, no I/O dependency |
| Object storage (disk write) | `core/parser/` module | Config (storage root path) | Local-disk v1; storage root from Settings |
| Document MERGE in Neo4j | `core/parser/` module | `GraphDB` (async driver) | PdfParser owns the write; GraphDB is the transport |
| Document Pydantic model extension | `core/schemas/models.py` | `core/models.py` (re-export shim) | Canonical path for new fields |
| Neo4j schema constraint | `core/database/migrations.py` | — | Already exists: `document_id_unique` on `Document.id` |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pypdf | ≥4.2 (latest: 6.12.2) | Text extraction from PDF | Already in pyproject.toml; R&D smoke-test validated on all 5 Cyrillic/EN resumes |
| hashlib | stdlib | SHA-256 of PDF bytes | No dependency; deterministic content hash |
| pathlib | stdlib | Path manipulation, mkdir, write_bytes | Idiomatic Python 3.11+ |
| asyncio | stdlib | run_in_executor for sync pypdf calls | Matches codebase async pattern |
| loguru | ≥0.7 | Structured logging; empty-page warnings | Already used everywhere |
| neo4j (AsyncDriver) | ≥5.20 | GraphDB.session() MERGE Document | Already in pyproject.toml |

[VERIFIED: pyproject.toml grep] pypdf>=4.2, neo4j>=5.20, loguru>=0.7 all declared in project.

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pdfplumber | ≥0.11 | Alternative extraction backend | Already in pyproject.toml; future backend implementation behind Protocol seam |
| tempfile + os.replace | stdlib | Atomic file write | Use for `.md` text file if crash-safety needed on write |

[VERIFIED: pyproject.toml] pdfplumber>=0.11 already declared — no new install step needed for when the seam is filled later.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pypdf | PyMuPDF (fitz) | PyMuPDF is C extension, more robust encoding, not in pyproject.toml — adds a dep; out of scope for v1 |
| Protocol for seam | ABC (abstract base class) | Protocol = structural subtyping = no inheritance requirement; simpler, idiomatic Python 3.11+ for this use case |
| `asyncio.run_in_executor` | `anyio.to_thread.run_sync` | anyio not in stack; run_in_executor is stdlib, sufficient here |

**Installation:** No new packages required. All dependencies already in `pyproject.toml`.

**Version verification:**
```
pypdf latest on PyPI: 6.12.2 (released May 2026)
pyproject.toml pin: >=4.2 → will install 6.12.2
```
[VERIFIED: PyPI + pyproject.toml]

---

## Architecture Patterns

### System Architecture Diagram

```
PDF file path (Path)
        │
        ▼
  PdfParser.parse(path)
        │
        ├─── 1. read PDF bytes ──► hashlib.sha256 ──► document_id (hex str)
        │
        ├─── 2. check Neo4j ──► MATCH (d:Document {id}) already exists?
        │         │                     │
        │         │               YES ──► return cached ParseResult (idempotent)
        │         │
        │         NO
        │
        ├─── 3. TextExtractorBackend.extract(path)
        │         │
        │         └── PyPdfBackend (default)
        │               PdfReader → per-page extract_text() → "--- PAGE i ---\n{text}"
        │               empty page detection → log warning → extraction_status
        │
        ├─── 4. Storage writes
        │         mkdir /storage/documents/{document_id}/
        │         copy original PDF  → {document_id}/{original_filename}
        │         write text.md      → {document_id}/text.md
        │
        └─── 5. GraphDB.session() MERGE Document node
                  MERGE (d:Document {id: document_id})
                  SET d.type, d.file_uri, d.text_uri,
                      d.parser_version, d.extraction_status,
                      d.ingested_at
                  │
                  └──► return ParseResult(document_id, extracted_text,
                                          file_uri, text_uri,
                                          extraction_status)
```

### Recommended Project Structure
```
core/
  parser/
    __init__.py          # re-exports PdfParser, ParseResult
    _backend.py          # TextExtractorBackend Protocol + PyPdfBackend
    pdf.py               # PdfParser class (public API)
tests/
  test_parser_unit.py    # unit: sha256, text formatting, empty-page handling (no infra)
  test_parser_integration.py  # integration: real PDFs in rnd/data/resume/, Neo4j MERGE
```

### Pattern 1: TextExtractorBackend Protocol (extraction seam)
**What:** A minimal `Protocol` defining the extraction contract. `PdfParser` depends only on the protocol, not a concrete class.
**When to use:** Every time the extraction backend needs to be swapped or tested in isolation.

```python
# core/parser/_backend.py
# Source: Python typing spec (https://typing.python.org/en/latest/spec/protocol.html)
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class TextExtractorBackend(Protocol):
    """Extraction seam — implement this to add pdfplumber, OCR, etc. later."""

    def extract(self, pdf_path: Path) -> tuple[str, str]:
        """
        Returns (extracted_text, extraction_status).
        extraction_status: "ok" | "empty"
        Never raises on image-only PDF — returns ("", "empty").
        """
        ...


class PyPdfBackend:
    """Concrete backend using pypdf. Satisfies TextExtractorBackend structurally."""

    PARSER_VERSION = "pypdf-v1"

    def extract(self, pdf_path: Path) -> tuple[str, str]:
        from pypdf import PdfReader
        from loguru import logger

        reader = PdfReader(str(pdf_path))
        pages: list[str] = []
        empty_pages: list[int] = []

        for i, page in enumerate(reader.pages, start=1):
            page_text = (page.extract_text() or "").strip()
            if not page_text:
                empty_pages.append(i)
            pages.append(f"--- PAGE {i} ---\n{page_text}")

        if empty_pages:
            logger.warning(
                "pdf_parser: empty pages detected file={} pages={}",
                pdf_path.name,
                empty_pages,
            )

        text = "\n\n".join(pages)
        status = "empty" if not text.strip() else "ok"
        return text, status
```

[VERIFIED: rnd/src/pdf_parser.py] Page marker style `--- PAGE i ---` and empty-page detection pattern confirmed from existing R&D code.

### Pattern 2: SHA-256 document_id for idempotency
**What:** Read all PDF bytes once, hash them. Use the hex digest as `document_id`. MERGE on this ID.
**When to use:** Whenever the same PDF file is uploaded again (idempotent by content, not filename).

```python
# Source: Python stdlib hashlib
import hashlib
from pathlib import Path

def compute_document_id(pdf_path: Path) -> str:
    data = pdf_path.read_bytes()
    return hashlib.sha256(data).hexdigest()
```

[ASSUMED] Returning the full 64-character hex digest as `document_id`. Planner may decide to truncate to 16 chars for human readability — either works since uniqueness requirement comes from sha256 collision resistance. MERGE key is `Document.id` per constraint `document_id_unique`.

### Pattern 3: Async PdfParser.parse() with sync CPU work offloaded
**What:** `parse()` is `async def` (required to await `GraphDB.session()`). The CPU-bound pypdf extraction runs in a thread executor to avoid blocking the event loop.
**When to use:** The codebase is fully async (FastAPI, neo4j async driver). pypdf is sync-only.

```python
# Source: Python asyncio docs
import asyncio
from functools import partial

async def parse(self, pdf_path: Path) -> ParseResult:
    loop = asyncio.get_running_loop()
    # Run sync extraction in thread pool
    extracted_text, status = await loop.run_in_executor(
        None,
        self._backend.extract,
        pdf_path,
    )
    # ... storage writes (also offload if large files become concern)
    # ... await Neo4j MERGE
```

[CITED: https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.run_in_executor]

### Pattern 4: Storage layout and file_uri / text_uri
**What:** All artifacts for one document live under a single directory keyed by `document_id`.
**Convention (Claude's Discretion):**
- Original PDF: `/storage/documents/{document_id}/{original_filename}` — preserves original name for debugging
- Extracted text: `/storage/documents/{document_id}/text.md`
- URIs stored as **relative paths** from the storage root (e.g., `documents/{document_id}/resume.pdf`) so the system is portable when moving from local disk to MinIO/S3 (per core_architecture.md §8).

```
/storage/
  documents/
    {sha256_hex}/
      resume.pdf          ← original PDF (original filename preserved)
      text.md             ← extracted text with page markers
```

[ASSUMED] Relative URI format is a recommendation. Planner should confirm whether to store absolute or relative path. Absolute is simpler for v1; relative is more portable for S3 migration.

### Pattern 5: MERGE Document node in Neo4j
**What:** Single idempotent Cypher query using MERGE on `Document.id`.
**When to use:** Every parse() call — even repeat calls do not create duplicates.

```cypher
MERGE (d:Document {id: $document_id})
SET d.type = $type,
    d.file_uri = $file_uri,
    d.text_uri = $text_uri,
    d.parser_version = $parser_version,
    d.extraction_status = $extraction_status,
    d.ingested_at = $ingested_at
```

The constraint `document_id_unique` on `Document.id` (from `core/database/migrations.py`) guarantees the MERGE target is unique. No separate dedup query needed.

[VERIFIED: core/database/migrations.py] `document_id_unique` constraint confirmed.

### Pattern 6: Document model extension (D-09)
**What:** Add three new optional fields to `core/schemas/models.py::Document`.

```python
# core/schemas/models.py  (additions to existing Document class)
class Document(BaseModel):
    id: str
    type: str | None = None            # resume / note / ats_field
    file_uri: str | None = None        # existing
    ingested_at: datetime | None = None  # existing
    created_at: datetime | None = None   # existing
    # --- new fields (D-09) ---
    text_uri: str | None = None        # path to .md text file
    parser_version: str | None = None  # e.g. "pypdf-v1"
    extraction_status: str | None = None  # "ok" | "empty"
```

No migration DDL needed — Neo4j is schema-optional for node properties; only the MERGE key (`id`) needs the existing unique constraint.

[VERIFIED: core/schemas/models.py] Current Document model has exactly `id, type, file_uri, ingested_at, created_at`.

### Pattern 7: ParseResult dataclass (return value of parse())
**What:** A lightweight return type — not the Pydantic Document model (which is the graph representation), but the result of a parse operation for callers.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ParseResult:
    document_id: str
    extracted_text: str
    file_uri: str
    text_uri: str
    extraction_status: str  # "ok" | "empty"
    parser_version: str
```

Success criteria from ROADMAP.md explicitly requires `PdfParser.parse(path)` to return an object with `extracted_text, document_id, file_uri, text_uri`.

### Anti-Patterns to Avoid

- **Storing text as `.txt`:** Locked decision D-04. Phase 5 extractor already validated with `.md` + page markers; changing format breaks downstream contract.
- **MERGE on file path or filename:** Only MERGE on `Document.id` (SHA-256 hex). File can be renamed; content cannot.
- **Calling GraphDB.session() before checking is_connected:** `session()` raises `RuntimeError` if `is_connected=False`. Guard with `if not self._db.is_connected` and either raise a domain-specific exception or log + skip Neo4j write (degraded mode per CLAUDE.md philosophy).
- **Blocking the async event loop with pypdf:** `PdfReader` is synchronous. Always offload to `run_in_executor`.
- **Importing PdfParser as a module-level singleton in route handlers:** Pattern from CLAUDE.md — inject via `app.state` or `Depends()`, not module-level globals.
- **Duplicating constraint definitions:** `document_id_unique` lives only in `core/database/migrations.py`. Do not re-declare in parser code.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PDF text extraction | Custom PDF byte parser | pypdf `PdfReader.extract_text()` | PDF format is complex; pypdf handles encoding tables, CMap, font mappings |
| Content hashing | Custom hash function | `hashlib.sha256` (stdlib) | Cryptographic strength; collision resistance proven |
| Async thread offload | Custom thread management | `asyncio.run_in_executor(None, fn, *args)` | Uses Python's default ThreadPoolExecutor; zero setup |
| Unique document MERGE | SELECT-then-INSERT logic | Cypher `MERGE (d:Document {id: $id})` | MERGE is atomic at DB level; SELECT-then-INSERT has TOCTOU race |
| Storage path computation | Home-grown UUID generator | SHA-256 hex as directory name | Self-documenting; deterministic; no extra state |

**Key insight:** All "hard" parts of this phase are solved by stdlib or existing project dependencies. The implementation risk is in correct async/sync boundary and graceful Neo4j degradation — not in the algorithms themselves.

---

## Common Pitfalls

### Pitfall 1: pypdf `extract_text()` returns `""` not `None` for image-only pages
**What goes wrong:** Code checks `if page_text is None` — always False because the return type is `str`.
**Why it happens:** pypdf API spec shows return type as `str`. The `or ""` guard in the R&D code is correct but the `is None` check would silently miss empty pages.
**How to avoid:** Use `(page.extract_text() or "").strip()` — handles both `""` and any future `None` edge case.
**Warning signs:** `extraction_status` is always `"ok"` even for scanned PDFs in your test corpus.

[VERIFIED: https://pypdf.readthedocs.io/en/stable/modules/PageObject.html — return type `str`]

### Pitfall 2: Cyrillic encoding issues with some PDFs
**What goes wrong:** `extract_text()` returns garbled characters or digits instead of Cyrillic letters for certain PDFs.
**Why it happens:** PDF format does not mandate a semantic text layer. Some PDFs use custom font encodings or CMap tables that pypdf cannot decode. This is a PDF quality issue, not a pypdf bug per se.
**How to avoid:** In the smoke-test all 5 Cyrillic Russian PDFs extracted cleanly with pypdf (R&D finding). For the production parser: log character count and flag suspiciously short extractions. Consider adding a `char_count` to logs for monitoring.
**Warning signs:** Very short `extracted_text` (< 100 chars) for a multi-page resume; extraction_status=`ok` but text looks like `"ÿÿÿÿ"`.

[VERIFIED: rnd/smoke_test_findings.md — all 5 Russian/EN PDFs extracted cleanly with pypdf]
[MEDIUM: GitHub issue #2330 — garbled chars reported on some PDFs, version 3.17.1; not reproduced on our corpus]

### Pitfall 3: Blocking async event loop with pypdf
**What goes wrong:** `PdfReader` is synchronous I/O + CPU. Calling it directly inside an `async def` without `run_in_executor` blocks the event loop while the PDF is read and parsed.
**Why it happens:** pypdf has no async API. Developers assume `async def` is sufficient.
**How to avoid:** Wrap `self._backend.extract(path)` in `await loop.run_in_executor(None, ...)`.
**Warning signs:** FastAPI endpoint response times degrade proportionally to PDF file size under load.

### Pitfall 4: GraphDB.session() raises if Neo4j is down
**What goes wrong:** `GraphDB.session()` raises `RuntimeError("Neo4j is not connected")`. If PdfParser doesn't handle this, the whole parse fails even though text extraction and storage writes succeeded.
**Why it happens:** `GraphDB.session()` has an explicit guard (`if self._driver is None or not self.is_connected: raise RuntimeError`).
**How to avoid:** Check `db.is_connected` before calling `session()`. On failure: log warning, return `ParseResult` without `document_id` or raise a domain exception. Do not crash the process.
**Warning signs:** Parse calls fail 100% when Neo4j is starting up / temporarily unavailable.

[VERIFIED: core/database/graph.py line 77-80]

### Pitfall 5: re-export shim must be updated
**What goes wrong:** `core/models.py` re-exports everything from `core.schemas.models`. If new fields are added to `Document` in `core/schemas/models.py`, the shim re-exports them automatically (wildcard or `from ... import Document`). But if any test or existing code imports `Document` from `core.models` and inspects the model fields, it needs to be aware the model changed.
**Why it happens:** D-09 extends the Document Pydantic model with 3 new optional fields.
**How to avoid:** New fields are all `Optional` with `None` defaults — backward compatible. No existing code breaks. Add test in `test_models_imports.py` pattern to verify new fields are accessible from both import paths.

[VERIFIED: core/models.py — re-export shim confirmed]

### Pitfall 6: Storage root not configurable
**What goes wrong:** Hard-coding `/storage/documents/` makes the parser unportable in CI (no write access), Docker bind-mounts, or Windows dev machines.
**Why it happens:** Path is assumed to be absolute and system-level.
**How to avoid:** Add `storage_root: Path = Field(default=Path("storage"))` to `Settings` (relative to cwd by default, overridable via env). `PdfParser` reads `get_settings().storage_root`. Planner should add this field to `core/config.py`.

[ASSUMED] Settings field name and default value — planner should choose. Risk: if not added, parser breaks in Docker/CI.

---

## Code Examples

### Full extraction backend (ready to port from R&D)

```python
# core/parser/_backend.py
# Source: rnd/src/pdf_parser.py (verified working on 5 Cyrillic/EN resumes)
from pathlib import Path
from typing import Protocol, runtime_checkable

from loguru import logger


@runtime_checkable
class TextExtractorBackend(Protocol):
    def extract(self, pdf_path: Path) -> tuple[str, str]: ...


class PyPdfBackend:
    PARSER_VERSION: str = "pypdf-v1"

    def extract(self, pdf_path: Path) -> tuple[str, str]:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        pages: list[str] = []
        empty_pages: list[int] = []

        for i, page in enumerate(reader.pages, start=1):
            page_text = (page.extract_text() or "").strip()
            if not page_text:
                empty_pages.append(i)
            pages.append(f"--- PAGE {i} ---\n{page_text}")

        if empty_pages:
            logger.warning(
                "empty pages detected file={} pages={}",
                pdf_path.name,
                empty_pages,
            )

        text = "\n\n".join(pages)
        status = "empty" if not text.strip() else "ok"
        return text, status
```

### MERGE Document node Cypher

```python
# Source: core/database/migrations.py pattern + core_architecture.md §5.1
MERGE_DOCUMENT_CYPHER = """
MERGE (d:Document {id: $document_id})
SET d.type = $type,
    d.file_uri = $file_uri,
    d.text_uri = $text_uri,
    d.parser_version = $parser_version,
    d.extraction_status = $extraction_status,
    d.ingested_at = $ingested_at
RETURN d
"""

async def _write_document_node(
    db: GraphDB,
    document_id: str,
    file_uri: str,
    text_uri: str,
    parser_version: str,
    extraction_status: str,
) -> None:
    from datetime import datetime, timezone

    async with db.session() as session:
        await session.run(
            MERGE_DOCUMENT_CYPHER,
            document_id=document_id,
            type="resume",
            file_uri=file_uri,
            text_uri=text_uri,
            parser_version=parser_version,
            extraction_status=extraction_status,
            ingested_at=datetime.now(timezone.utc).isoformat(),
        )
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| PyPDF2 (deprecated) | pypdf (successor package) | 2022 | Same API surface; `from pypdf import PdfReader` — R&D already uses new package name |
| `text.txt` output | `text.md` with page markers | D-04/D-05 decision | Phase 5 extractor expects `.md` format |
| Hard-crash on parse failure | Graceful degradation (D-07/D-08) | Project philosophy | `extraction_status` field carries failure signal |

**Deprecated/outdated:**
- `PyPDF2`: superseded by `pypdf`. The R&D code already imports from `pypdf`, not `PyPDF2`.
- `page.extractText()` (CamelCase): old PyPDF2 API. Current API is `page.extract_text()` (snake_case).

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Returning full SHA-256 hex (64 chars) as `document_id` | Pattern 2 | Low — uniqueness is preserved regardless of length; planner may truncate |
| A2 | Storing URIs as relative paths from storage root | Pattern 4 | Medium — if absolute, S3 migration requires a data migration to strip host prefix |
| A3 | `storage_root` should be added to `Settings` as a new env-configurable field | Pitfall 6 | High — without this, CI/Docker deployments cannot configure storage location |
| A4 | Graceful Neo4j degradation on parse: log + return partial result without neo4j write, do not crash | Pitfall 4 | Medium — alternative is to raise domain exception; planner should decide behavior explicitly |
| A5 | `ParseResult` is a `dataclass(frozen=True)`, not a Pydantic model | Pattern 7 | Low — either works; dataclass is lighter since no validation needed on output |

---

## Open Questions (RESOLVED during planning)

> RESOLVED #1: Neo4j-down → log warning + return full ParseResult, no exception (graceful degradation per CLAUDE.md; supersedes the DocumentNodeWriteError recommendation below).
> RESOLVED #2: storage_root → relative `Path("storage")` default, env-overridable via `STORAGE_ROOT`.
> RESOLVED #3: document_id → full 64-char SHA-256 hex.

1. **Storage graceful degradation: what does PdfParser return when Neo4j is down?**
   - What we know: GraphDB.session() raises RuntimeError if not connected.
   - What's unclear: Should parse() (a) raise, (b) return ParseResult with a warning and no document_id, or (c) skip the MERGE and return partial result?
   - Recommendation: Return full ParseResult (text+files saved) and raise a specific `DocumentNodeWriteError` exception that callers can catch. The files are already saved — only the graph write failed. This matches graceful-degradation philosophy: the data is not lost.

2. **Should `storage_root` be absolute or relative in Settings?**
   - What we know: `core_architecture.md` plans LocalDisk → MinIO/S3 migration.
   - What's unclear: Relative (`Path("storage")` → resolves to cwd) vs absolute (`/storage`).
   - Recommendation: Use `Path("storage")` as default (relative to project root), overridable via `STORAGE_ROOT` env var. Works cross-platform and in Docker with bind-mount.

3. **Should `document_id` be the full 64-char SHA-256 hex or a truncated form?**
   - What we know: MERGE key must be globally unique. SHA-256 collision probability is negligible.
   - What's unclear: Human readability of 64-char IDs vs truncated 16-char.
   - Recommendation: Use full 64 chars. The ID is machine-consumed (file paths, Neo4j keys). No human needs to type it.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pypdf | PARSE-01 text extraction | ✓ (in pyproject.toml) | >=4.2 (6.12.2 latest) | — |
| neo4j async driver | PARSE-03 Document MERGE | ✓ (in pyproject.toml) | >=5.20 | Degraded mode (no graph write) |
| hashlib | SHA-256 document_id | ✓ stdlib | 3.11 | — |
| pathlib | Storage writes | ✓ stdlib | 3.11 | — |
| loguru | Structured logging | ✓ (in pyproject.toml) | >=0.7 | — |
| /storage/ directory | File persistence | ✗ (must be created) | — | mkdir in Wave 0 / Docker volume |

**Missing dependencies with no fallback:**
- `/storage/` directory: must be created (gitignored or Docker volume). Wave 0 task.

**Missing dependencies with fallback:**
- neo4j unreachable: parser falls back to degraded mode (saves files, skips MERGE).

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.2 + pytest-asyncio 0.23 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (asyncio_mode=auto) |
| Quick run command | `pytest tests/test_parser_unit.py -x` |
| Full suite command | `pytest tests/ --cov=core/parser` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PARSE-01 | extract_text returns non-empty string from a text-PDF | unit | `pytest tests/test_parser_unit.py::test_pypdf_backend_extracts_text -x` | ❌ Wave 0 |
| PARSE-01 | page markers `--- PAGE 1 ---` present in output | unit | `pytest tests/test_parser_unit.py::test_page_markers_format -x` | ❌ Wave 0 |
| PARSE-01 | image-only PDF (or all-empty pages) returns status=empty, no crash | unit | `pytest tests/test_parser_unit.py::test_empty_pdf_graceful -x` | ❌ Wave 0 |
| PARSE-01 | extraction_status=ok for valid PDF, empty for blank | unit | `pytest tests/test_parser_unit.py::test_extraction_status -x` | ❌ Wave 0 |
| PARSE-02 | PDF file saved at /storage/documents/{id}/{filename} | unit | `pytest tests/test_parser_unit.py::test_storage_layout -x` | ❌ Wave 0 |
| PARSE-02 | text.md saved at /storage/documents/{id}/text.md | unit | `pytest tests/test_parser_unit.py::test_text_md_saved -x` | ❌ Wave 0 |
| PARSE-02 | re-parse same PDF → same document_id (SHA-256 idempotency) | unit | `pytest tests/test_parser_unit.py::test_sha256_idempotent -x` | ❌ Wave 0 |
| PARSE-03 | Document node exists in Neo4j after parse | integration | `pytest tests/test_parser_integration.py::test_document_node_created -x` | ❌ Wave 0 |
| PARSE-03 | Re-parse same PDF → no duplicate Document node | integration | `pytest tests/test_parser_integration.py::test_document_node_idempotent -x` | ❌ Wave 0 |
| PARSE-03 | Document.text_uri, parser_version, extraction_status all set | integration | `pytest tests/test_parser_integration.py::test_document_node_fields -x` | ❌ Wave 0 |
| PARSE-01 + all | Parse all 5 rnd/data/resume/ PDFs — no crash, non-empty text | integration | `pytest tests/test_parser_integration.py::test_rnd_corpus_smoke -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_parser_unit.py -x`
- **Per wave merge:** `pytest tests/ -x --cov=core/parser --cov-report=term-missing`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_parser_unit.py` — covers PARSE-01 (text extraction), PARSE-02 (storage), SHA-256 idempotency (no infra needed; uses tmp_path fixture)
- [ ] `tests/test_parser_integration.py` — covers PARSE-03 (Neo4j MERGE); requires running Neo4j; uses session-scoped `neo4j_driver` from `conftest.py`
- [ ] `storage/` directory creation — needed for integration tests (add to `conftest.py` or test fixture with `tmp_path`)

*(No framework install gaps — pytest + pytest-asyncio already declared in pyproject.toml dev extras)*

---

## Security Domain

> `security_enforcement` not set in config.json — treated as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — (no auth in parser module) |
| V3 Session Management | no | — |
| V4 Access Control | no | — (no multi-user in v1) |
| V5 Input Validation | yes | Validate PDF file extension + non-empty bytes before processing |
| V6 Cryptography | yes | hashlib.sha256 (stdlib, FIPS-approved) — never hand-roll |

### Known Threat Patterns for PDF parsing stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed PDF (zip bomb, quine) | Denial of Service | pypdf has size/depth limits; add max file size check before reading |
| Path traversal via original_filename | Tampering / EoP | Sanitize filename: use `Path(original_filename).name` only, never trust full path |
| Arbitrary file overwrite via document_id | Tampering | document_id is SHA-256 hex (0-9a-f only) — safe as directory name |

---

## Sources

### Primary (HIGH confidence)
- `rnd/src/pdf_parser.py` — extraction logic, page marker format, empty-page pattern — VERIFIED by reading
- `rnd/smoke_test_findings.md` — 5/5 Cyrillic/EN resumes extracted cleanly with pypdf — VERIFIED by reading
- `core/database/migrations.py` — `document_id_unique` constraint confirmed — VERIFIED by reading
- `core/database/graph.py` — `GraphDB.session()` raises on not_connected — VERIFIED by reading
- `core/schemas/models.py` — current Document model fields — VERIFIED by reading
- `pyproject.toml` — dependency versions and test config — VERIFIED by reading
- [pypdf PageObject docs](https://pypdf.readthedocs.io/en/stable/modules/PageObject.html) — `extract_text() -> str` return type
- [Python typing Protocol spec](https://typing.python.org/en/latest/spec/protocol.html) — Protocol + runtime_checkable pattern

### Secondary (MEDIUM confidence)
- [pypdf text extraction guide](https://pypdf.readthedocs.io/en/stable/user/extract-text.html) — extraction modes, visitor API, image-only PDF handling
- [PyPI pypdf](https://pypi.org/project/pypdf/) — latest version 6.12.2
- [Python asyncio run_in_executor](https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.run_in_executor) — sync-in-async pattern

### Tertiary (LOW confidence)
- [GitHub issue #2330](https://github.com/py-pdf/pypdf/issues/2330) — garbled chars reported (v3.17.1, not reproduced on our corpus)
- [GitHub issue #375](https://github.com/mstamy2/PyPDF2/issues/375) — old PyPDF2 Cyrillic issue; may not apply to current pypdf 6.x

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries in pyproject.toml, R&D validated on real data
- Architecture: HIGH — patterns derived from existing codebase conventions + Python typing spec
- Pitfalls: MEDIUM-HIGH — empty-page behavior VERIFIED via docs; Cyrillic issues are LOW from old GitHub issues not reproduced on corpus
- Test map: HIGH — test names and commands are concrete and specific

**Research date:** 2026-06-03
**Valid until:** 2026-07-03 (pypdf releases frequently; re-verify version before planning if > 30 days)
