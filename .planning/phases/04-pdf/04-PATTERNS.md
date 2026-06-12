# Phase 4: PDF-парсер - Pattern Map

**Mapped:** 2026-06-03
**Files analyzed:** 9
**Analogs found:** 9 / 9

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `core/parser/__init__.py` | module re-export | — | `core/models.py` | exact (re-export shim pattern) |
| `core/parser/_backend.py` | utility (extraction seam) | file-I/O | `rnd/src/pdf_parser.py` | exact (same pypdf + page-marker logic) |
| `core/parser/pdf.py` | service | file-I/O + CRUD (Neo4j write) | `core/database/graph.py` + `scripts/seed.py` | role-match (async service with GraphDB session) |
| `core/schemas/models.py` | model (extension) | — | `core/schemas/models.py` itself (Document class) | exact (same file, field extension) |
| `core/models.py` | re-export shim | — | `core/models.py` itself | exact (add Document fields remain auto-exported) |
| `core/config.py` | config (extension) | — | `core/config.py` itself (Settings class) | exact (same file, new Field) |
| `tests/test_parser_unit.py` | test (unit) | file-I/O | `tests/test_migrations.py` | role-match (pytest-asyncio, session loop scope) |
| `tests/test_parser_integration.py` | test (integration) | file-I/O + CRUD | `tests/test_migrations.py` | exact (async session-scoped fixtures, GraphDB, pytestmark) |
| `tests/conftest.py` | test fixture | — | `tests/conftest.py` itself | exact (add graph_db fixture following test_migrations.py pattern) |

---

## Pattern Assignments

### `core/parser/__init__.py` (module re-export)

**Analog:** `core/models.py` (lines 1-34)

**Re-export pattern** (full file):
```python
# core/models.py — explicit named re-exports from canonical submodule
from core.schemas.models import (
    Candidate,
    ...
    Document,
    ...
)

__all__ = [
    "Candidate",
    ...
    "Document",
    ...
]
```

**Apply:** `core/parser/__init__.py` should re-export `PdfParser` and `ParseResult` from `core.parser.pdf` using the same explicit `__all__` style. Do NOT re-export `_backend` internals.

```python
# core/parser/__init__.py — target pattern
from core.parser.pdf import ParseResult, PdfParser

__all__ = ["PdfParser", "ParseResult"]
```

---

### `core/parser/_backend.py` (utility, file-I/O)

**Analog:** `rnd/src/pdf_parser.py` (full file, 44 lines)

**Imports pattern** (lines 1-5):
```python
from pathlib import Path

from loguru import logger
from pypdf import PdfReader
```

**Core extraction pattern** (lines 7-34):
```python
def pdf_to_text(path: str | Path) -> str:
    pdf_path = Path(path)
    reader = PdfReader(str(pdf_path))
    pages: list[str] = []
    empty_pages: list[int] = []
    for i, page in enumerate(reader.pages, start=1):
        # Some pages can be image-only; extract_text() then returns None.
        page_text = (page.extract_text() or "").strip()
        if not page_text:
            empty_pages.append(i)
        pages.append(f"--- PAGE {i} ---\n{page_text}")

    result = "\n\n".join(pages)
    logger.info(
        "pdf_to_text: {} — pages={}, chars={}, empty_pages={}",
        pdf_path.name,
        len(pages),
        len(result),
        empty_pages or "none",
    )
    return result
```

**Notes for new file:**
- Wrap `pdf_to_text` logic into a `PyPdfBackend` class with method `extract(self, pdf_path: Path) -> tuple[str, str]` returning `(text, extraction_status)`.
- Add a `TextExtractorBackend` Protocol above it (structural subtyping seam per D-02).
- Keep `--- PAGE {i} ---` marker style exactly (D-05).
- Keep `(page.extract_text() or "").strip()` guard (Pitfall 1 in RESEARCH.md).
- Add `PARSER_VERSION: str = "pypdf-v1"` class attribute.
- Move `from pypdf import PdfReader` inside the method body to keep module import fast (R&D pattern implies local import is fine).
- The `extract()` return status is `"empty"` if `not text.strip()` else `"ok"` (D-08).

---

### `core/parser/pdf.py` (service, file-I/O + CRUD)

**Analogs:**
- `core/database/graph.py` — async class pattern with `GraphDB.session()` context manager
- `scripts/seed.py` — direct `get_settings()` usage + async Neo4j MERGE pattern
- `core/database/migrations.py` — graceful degradation guard (`if not self.db.is_connected`)

**Imports pattern** — assemble from analogs:
```python
# From core/database/graph.py lines 1-8:
import asyncio
from loguru import logger
from neo4j import AsyncSession

# From scripts/seed.py lines 13-17:
from core.config import get_settings
from core.database.graph import GraphDB

# New for pdf.py:
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING
```

**Graceful degradation guard** — from `core/database/migrations.py` lines 107-109:
```python
async def apply_all(self) -> None:
    if not self.db.is_connected:
        logger.warning("Neo4j unavailable — skipping schema migration")
        return
```
Apply same pattern in `PdfParser.parse()`: check `db.is_connected` before calling `db.session()`, log warning + skip MERGE instead of crashing.

**Async MERGE session pattern** — from `scripts/seed.py` lines 360-365:
```python
async with db.session() as session:
    await _seed_candidate(session)
```
And `core/database/migrations.py` lines 111-117:
```python
async with self.db.session() as session:
    for name, cypher in CONSTRAINTS:
        await session.run(cypher)
        logger.debug("constraint applied: {}", name)
```

**GraphDB.session() raises guard** — `core/database/graph.py` lines 82-83:
```python
if self._driver is None or not self.is_connected:
    raise RuntimeError("Neo4j is not connected - cannot create session")
```
This is why the `is_connected` check in `PdfParser` must happen *before* entering `db.session()`.

**Document MERGE Cypher** — assembled from `scripts/seed.py` lines 166-174 (existing Document MERGE pattern):
```python
await session.run(
    "MERGE (n:Document {id: $id}) "
    "ON CREATE SET n.type=$type, n.file_uri=$file_uri "
    "ON MATCH SET n.type=$type, n.file_uri=$file_uri",
    id="doc-001",
    type="resume",
    file_uri="storage/documents/doc-001/resume.pdf",
)
```
Extend with the new fields from D-09: `text_uri`, `parser_version`, `extraction_status`, `ingested_at`. Use `SET` (not `ON CREATE SET`) so re-parse updates fields idempotently:
```cypher
MERGE (d:Document {id: $document_id})
SET d.type = $type,
    d.file_uri = $file_uri,
    d.text_uri = $text_uri,
    d.parser_version = $parser_version,
    d.extraction_status = $extraction_status,
    d.ingested_at = $ingested_at
```

**Direct `get_settings()` pattern** — `scripts/seed.py` lines 351-352:
```python
async def main() -> None:
    settings = get_settings()
    db = GraphDB(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
    )
```
`PdfParser` is not a CLI script, so it receives `GraphDB` via constructor injection — but storage_root comes from `get_settings().storage_root` (CLAUDE.md: scripts use direct `get_settings()`; the parser module follows the same pattern for settings access, not FastAPI DI).

**run_in_executor pattern** — asyncio stdlib, apply to wrap sync pypdf call:
```python
loop = asyncio.get_running_loop()
extracted_text, status = await loop.run_in_executor(
    None,
    self._backend.extract,
    pdf_path,
)
```

**Loguru structured log style** — from `core/database/graph.py` lines 49, 52, 58:
```python
logger.info("Neo4j connected on attempt {}/{}", attempt, retries)
logger.warning("Neo4j ping failed (attempt {}/{}): {}", attempt, retries, exc)
logger.error("Neo4j unavailable after {} attempts - running in degraded mode", retries)
```
Use `{}` positional placeholders (never f-strings in logger calls) — project-wide Loguru convention.

---

### `core/schemas/models.py` — Document class extension (model, D-09)

**Analog:** `core/schemas/models.py` lines 82-88 (current Document class)

**Current Document class** (lines 82-88):
```python
class Document(BaseModel):
    id: str
    type: str | None = None  # resume / note / ats_field
    file_uri: str | None = None
    ingested_at: datetime | None = None
    created_at: datetime | None = None
```

**Extension pattern** — follow the same `field: type | None = None` style used for every optional field in all 12 models. Inline comment explains value set:
```python
class Document(BaseModel):
    id: str
    type: str | None = None  # resume / note / ats_field
    file_uri: str | None = None
    ingested_at: datetime | None = None
    created_at: datetime | None = None
    # --- added in Phase 4 (PDF parser) ---
    text_uri: str | None = None            # path to extracted .md text file
    parser_version: str | None = None     # e.g. "pypdf-v1"
    extraction_status: str | None = None  # "ok" | "empty"
```

**Field ordering convention:** New optional fields appended at the bottom, `id` stays first (required, no default).

**No migration DDL needed** — Neo4j is schema-optional for node properties. Only the MERGE key (`id`) needs the existing `document_id_unique` constraint in `core/database/migrations.py`. Do NOT add anything to that file.

---

### `core/models.py` — re-export shim (no changes needed)

**Analog:** `core/models.py` lines 1-34 (full file)

The shim does an explicit named import of `Document`:
```python
from core.schemas.models import (
    ...
    Document,
    ...
)
```
When `Document` gains new fields in `core/schemas/models.py`, those fields are automatically available via `core.models.Document` — no change to `core/models.py` is needed. Verify this in `tests/test_models_imports.py` (see test file section below).

---

### `core/config.py` — Settings extension (config)

**Analog:** `core/config.py` lines 7-33 (Settings class)

**Field declaration pattern** (lines 14-27):
```python
neo4j_uri: str = Field(default="bolt://localhost:7687", description="Neo4j Bolt URI")
neo4j_user: str = Field(default="neo4j", description="Neo4j username")
neo4j_password: str = Field(description="Neo4j password — обязательно в .env")
```

**New field to add** — follow identical `Field(default=..., description=...)` style:
```python
from pathlib import Path

# in Settings class body, after redis_url:
storage_root: Path = Field(
    default=Path("storage"),
    description="Root directory for document storage (relative to cwd or absolute)",
)
```

**`model_config`** (lines 29-33) — unchanged, `SettingsConfigDict` already handles `case_sensitive=False` so the env var `STORAGE_ROOT` maps automatically.

**lru_cache** (lines 36-42) — unchanged, `get_settings.cache_clear()` in tests will clear the new field too.

---

### `tests/test_parser_unit.py` (test, unit)

**Analog:** `tests/test_migrations.py` (full file, 65 lines)

**Module-level asyncio scope mark** (line 10):
```python
pytestmark = pytest.mark.asyncio(loop_scope="session")
```
Apply this to `test_parser_unit.py` even though unit tests don't use Neo4j — the test suite runs with session-scoped fixtures from conftest.py and consistency prevents loop-scope conflicts.

**tmp_path fixture pattern** — pytest built-in, use for storage writes without touching real disk:
```python
def test_storage_layout(tmp_path: Path) -> None:
    # create a minimal PDF bytes fixture or use rnd/data/resume/*.pdf
    ...
    parser = PdfParser(db=None, storage_root=tmp_path)  # or mock
```

**Import pattern** — follow `tests/test_migrations.py` lines 1-9:
```python
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio

from core.config import Settings
from core.database.graph import GraphDB
# replace above with parser imports:
from core.parser import ParseResult, PdfParser
from core.parser._backend import PyPdfBackend
```

**Unit test structure** — no infra fixtures needed; use `tmp_path` for storage:
- `test_pypdf_backend_extracts_text` — `PyPdfBackend().extract(pdf_path)` returns non-empty string
- `test_page_markers_format` — `"--- PAGE 1 ---"` in extracted text
- `test_empty_pdf_graceful` — all-blank input → status `"empty"`, no exception
- `test_sha256_idempotent` — same bytes → same document_id
- `test_storage_layout` — files written to `tmp_path/documents/{id}/`
- `test_extraction_status_ok` — normal PDF → `"ok"`

---

### `tests/test_parser_integration.py` (test, integration)

**Analog:** `tests/test_migrations.py` (full file, 65 lines) — closest match

**Mandatory module-level mark** (line 10) — MUST include, required by CLAUDE.md for session-scoped async fixtures:
```python
pytestmark = pytest.mark.asyncio(loop_scope="session")
```

**Session-scoped GraphDB fixture** (lines 13-22) — copy and adapt:
```python
@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def graph_db(settings: Settings) -> AsyncGenerator[GraphDB, None]:
    db = GraphDB(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
    )
    await db.connect_with_retry(retries=1, delays=[0])
    yield db
    await db.close()
```
This fixture is needed by `test_parser_integration.py`; it can live in `conftest.py` or locally. If added to `conftest.py`, follow the same `pytest_asyncio.fixture(loop_scope="session", scope="session")` decorator pattern.

**Integration test bodies** — pattern from `test_migrations.py` lines 32-49:
```python
async def test_document_node_created(graph_db: GraphDB, tmp_path: Path) -> None:
    parser = PdfParser(db=graph_db, storage_root=tmp_path)
    result = await parser.parse(Path("rnd/data/resume/<any>.pdf"))

    async with graph_db.session() as session:
        r = await session.run(
            "MATCH (d:Document {id: $id}) RETURN d", id=result.document_id
        )
        record = await r.single()
    assert record is not None
```

**Corpus smoke test** — iterate `rnd/data/resume/` using `Path.glob("*.pdf")`, similar to how `test_migrations.py` verifies all named constraints in a loop.

---

## Shared Patterns

### Loguru structured logging
**Source:** `core/database/graph.py` lines 49, 52, 58-61
**Apply to:** `core/parser/_backend.py`, `core/parser/pdf.py`
```python
logger.info("pdf_parser: reading {}", pdf_path.name)
logger.warning("pdf_parser: empty pages file={} pages={}", pdf_path.name, empty_pages)
logger.info("pdf_parser: done file={} chars={} status={}", pdf_path.name, len(text), status)
logger.warning("pdf_parser: Neo4j unavailable — document node not persisted id={}", doc_id)
```
Convention: `{}` positional placeholders, never f-strings inside logger calls. Context key=value pairs in the message string.

### Graceful degradation (is_connected guard)
**Source:** `core/database/migrations.py` lines 107-109
**Apply to:** `core/parser/pdf.py` before every `db.session()` call
```python
if not self._db.is_connected:
    logger.warning("Neo4j unavailable — document node not persisted id={}", document_id)
    return result  # files already saved; return ParseResult without raising
```

### Direct `get_settings()` — not FastAPI DI
**Source:** `scripts/seed.py` line 351; `scripts/migrate.py` (same pattern)
**Apply to:** `core/parser/pdf.py` if `PdfParser` needs to read `storage_root` internally when no settings injected. Prefer constructor injection `PdfParser(db, storage_root)` but fall back to `get_settings().storage_root` as default.
```python
from core.config import get_settings

class PdfParser:
    def __init__(
        self,
        db: GraphDB,
        storage_root: Path | None = None,
        backend: TextExtractorBackend | None = None,
    ) -> None:
        self._db = db
        self._storage_root = storage_root or get_settings().storage_root
        self._backend = backend or PyPdfBackend()
```

### MERGE on `.id` only — never on filename or path
**Source:** `core/database/migrations.py` constraint `document_id_unique` (line 62-65); `scripts/seed.py` Document MERGE line 167
**Apply to:** `core/parser/pdf.py` MERGE cypher — key must be `{id: $document_id}` (SHA-256 hex). Original filename is stored as a property, never as a MERGE key.

### Async session context manager
**Source:** `core/database/graph.py` lines 76-86; `core/database/migrations.py` lines 111-117
**Apply to:** `core/parser/pdf.py` Neo4j write step
```python
async with self._db.session() as session:
    await session.run(MERGE_DOCUMENT_CYPHER, **params)
```

### pytest session loop scope mark
**Source:** `tests/test_migrations.py` line 10
**Apply to:** `tests/test_parser_integration.py` (mandatory); `tests/test_parser_unit.py` (recommended for consistency)
```python
pytestmark = pytest.mark.asyncio(loop_scope="session")
```

---

## No Analog Found

All files have close analogs in the codebase. No entries.

---

## Metadata

**Analog search scope:** `core/`, `scripts/`, `tests/`, `rnd/src/`
**Files scanned:** 10 source files read
**Analogs identified:** 5 distinct analog files covering all 9 classified files
**Pattern extraction date:** 2026-06-03
