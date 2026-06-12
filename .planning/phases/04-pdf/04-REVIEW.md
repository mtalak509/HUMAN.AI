---
phase: 04-pdf
reviewed: 2026-06-11T00:00:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - core/config.py
  - core/parser/__init__.py
  - core/parser/_backend.py
  - core/parser/pdf.py
  - core/schemas/models.py
  - tests/conftest.py
  - tests/test_parser_unit.py
  - tests/test_parser_integration.py
  - tests/test_models_imports.py
findings:
  critical: 1
  warning: 5
  info: 4
  total: 10
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-06-11
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Phase 4 adds the PDF extraction seam (`TextExtractorBackend` Protocol + `PyPdfBackend`), the async `PdfParser` with SHA-256 content addressing, a filesystem storage layer, and a Neo4j `Document` MERGE with graceful degradation. The structure is clean and conventions are mostly respected: MERGE is keyed on `.id` only with bound parameters (no Cypher injection), Loguru `{}` placeholders are used, graceful degradation is honored, and `get_settings()` caching is intact.

The dominant defect is **unhandled extraction failure**: `PyPdfBackend.extract()` calls `PdfReader(...)` and `page.extract_text()`, both of which raise on corrupt, truncated, or encrypted PDFs. `PdfParser.parse()` does not catch these, so a single malformed input crashes the caller — and the `parse()` docstring actively misrepresents the raised exceptions, which will mislead callers writing error handling. For an ingestion pipeline that processes arbitrary uploaded resumes, this is a correctness/robustness BLOCKER. Several lesser issues (ordering of writes vs. extraction, empty-text persistence, redundant/misleading "sanitization") are documented below.

## Critical Issues

### CR-01: Unhandled exceptions on corrupt/encrypted/truncated PDFs crash `parse()`; docstring is wrong

**File:** `core/parser/_backend.py:57-66`, `core/parser/pdf.py:100-126`
**Issue:**
`PyPdfBackend.extract()` runs `PdfReader(str(pdf_path))` (line 59) and `page.extract_text()` (line 66). pypdf raises on:
- encrypted/password-protected PDFs (`pypdf.errors.FileNotDecryptedError` / `DependencyError` if AES libs missing),
- corrupt or truncated files (`pypdf.errors.PdfReadError`, `EmptyFileError`),
- non-PDF bytes that happen to carry a `.pdf` suffix (the suffix check at `pdf.py:113` is the only gate — content is never validated).

The Protocol contract (`_backend.py:28-30`) only guarantees no-raise for *image-only* PDFs, not for malformed input. `PdfParser.parse()` calls `extract` through `run_in_executor` (`pdf.py:122`) with no try/except, so the exception propagates synchronously to the awaiting caller. In an ingestion pipeline fed arbitrary uploads, one bad file aborts the operation.

Compounding the bug: the `parse()` docstring (`pdf.py:100-102`) claims `Raises: FileNotFoundError ... ValueError`, implying those are the *only* raised types. A caller who writes `except (FileNotFoundError, ValueError)` based on this contract will let `PdfReadError`/`FileNotDecryptedError` escape uncaught.

**Fix:** Wrap the extraction call and degrade to an explicit error status rather than crashing, OR document and intentionally propagate. Recommended (degrade, mirroring the empty-PDF pattern):
```python
# core/parser/_backend.py — in PyPdfBackend.extract
from pypdf.errors import PdfReadError, FileNotDecryptedError, EmptyFileError

try:
    reader = PdfReader(str(pdf_path))
    # ... existing per-page loop ...
except (PdfReadError, FileNotDecryptedError, EmptyFileError) as exc:
    logger.warning("pdf_parser: unreadable PDF file={} err={}", pdf_path.name, exc)
    return "", "error"
```
Then add `"error"` to the allowed `extraction_status` set everywhere it is asserted/validated (`models.py:91` comment, `test_parser_integration.py:83`, `test_parser_unit.py`), and correct the `parse()` docstring's `Raises:` section to list the real exception surface (or state that extraction failures are surfaced as `extraction_status="error"`, never raised).

## Warnings

### WR-01: Storage writes happen *after* extraction, but DB MERGE failure is silent — partial-state asymmetry

**File:** `core/parser/pdf.py:128-177`
**Issue:**
Files are written (lines 136, 139) before the Document MERGE (lines 166-176). If `session.run()` raises (transient Neo4j error mid-transaction, constraint violation, network blip *after* `is_connected` was last `True`), the exception propagates uncaught from `parse()`: files are on disk but no node exists and the caller receives an exception rather than a `ParseResult`. This violates the stated invariant "a Neo4j outage never loses data" (comment line 157) for the *transient-failure-during-write* case — graceful degradation only covers the `is_connected is False` pre-check (line 160), not an exception thrown by `session.run` itself.
**Fix:** Wrap the MERGE in try/except so a write failure degrades the same way an unavailable DB does:
```python
else:
    try:
        async with self._db.session() as session:
            await session.run(MERGE_DOCUMENT_CYPHER, ...)
        logger.info("pdf_parser: document node merged id={}", document_id)
    except Exception as exc:
        logger.warning("pdf_parser: document MERGE failed id={} err={}", document_id, exc)
```

### WR-02: `extraction_status="empty"` still writes an empty `text.md` and MERGEs a node — silent data-quality hole

**File:** `core/parser/pdf.py:139, 166-176`
**Issue:** When extraction yields `("", "empty")` (image-only PDF), `text.md` is written as a zero-byte file and a `Document` node is MERGEd with `extraction_status="empty"`. Downstream consumers (the LLM extractor) will read an empty text file. Nothing flags this for re-processing (e.g. OCR), and `test_rnd_corpus_smoke` (`test_parser_integration.py:108-114`) explicitly *accepts* `"empty"` as success. An image-only resume is silently ingested as a content-free document. At minimum this should be logged at WARNING from `parse()` (currently only the per-page WARNING in the backend fires), so empty ingests are visible in prod logs.
**Fix:** Add an explicit branch in `parse()`:
```python
if status == "empty":
    logger.warning("pdf_parser: no extractable text (image-only?) id={} file={}", document_id, safe_name)
```

### WR-03: `safe_name` "sanitization" is a no-op and the security comment is misleading

**File:** `core/parser/pdf.py:129-130, 142`
**Issue:** `safe_name = Path(pdf_path.name).name` is redundant — `Path.name` already returns only the final path component with no separators, so wrapping it in `Path(...).name` strips nothing additional. The comment "Sanitize filename against path traversal (Security T-04-02)" overstates the protection: this does not handle a filename that is literally `..` or names containing characters illegal on the target filesystem, and `file_uri` (line 142) is built by string interpolation of this value. The actual traversal safety comes from `document_id` being hex (the directory level), not from this line. Misleading security comments invite future regressions.
**Fix:** Either drop the redundant wrap and rely on the hex `document_id` directory plus an explicit reject of degenerate names, or make the sanitization real:
```python
safe_name = Path(pdf_path.name).name
if safe_name in {"", ".", ".."} or "/" in safe_name or "\\" in safe_name:
    raise ValueError(f"Unsafe PDF filename: {pdf_path.name!r}")
```
Adjust the comment to state what is actually guaranteed.

### WR-04: `parser_version` resolved via `getattr` fallback can desync from the node's recorded version

**File:** `core/parser/pdf.py:146`
**Issue:** `parser_version = getattr(self._backend, "PARSER_VERSION", "pypdf-v1")`. A custom backend injected via the D-02 seam that lacks a `PARSER_VERSION` attribute will silently record `"pypdf-v1"` on the Document node despite *not* being pypdf. This corrupts provenance (the node claims it was parsed by pypdf-v1 when it was not), defeating the purpose of recording `parser_version`. The hardcoded fallback string is also a magic value duplicated from `_backend.py:45`.
**Fix:** Make `PARSER_VERSION` part of the `TextExtractorBackend` Protocol contract so every backend must declare it, and drop the silent fallback (or fall back to `type(self._backend).__name__` so the recorded value is at least truthful):
```python
parser_version = getattr(self._backend, "PARSER_VERSION", None) or type(self._backend).__name__
```

### WR-05: `Document` MERGE writes `ingested_at` but never `created_at`; model declares both

**File:** `core/parser/pdf.py:30-39, 170-175`; `core/schemas/models.py:82-91`
**Issue:** The `Document` Pydantic model declares both `ingested_at` and `created_at` (`models.py:86-87`). The MERGE sets `ingested_at` (line 175) but not `created_at`, and uses unconditional `SET` (not `ON CREATE SET`) for `ingested_at` — so re-parsing the same PDF overwrites `ingested_at` with a new timestamp on every run. The result: there is no stable record of when the document *first* entered the graph (`created_at` stays null forever, `ingested_at` moves on every re-parse). For a provenance-centric design (CLAUDE.md: Fact-node provenance), losing first-seen time is a real gap.
**Fix:** Use `ON CREATE SET d.created_at = $now` alongside the idempotent `SET` for the mutable fields:
```cypher
MERGE (d:Document {id: $document_id})
ON CREATE SET d.created_at = $now
SET d.type = $type, d.file_uri = $file_uri, ...
    d.ingested_at = $now
RETURN d
```

## Info

### IN-01: `MERGE_DOCUMENT_CYPHER` `RETURN d` result is never consumed or used

**File:** `core/parser/pdf.py:38, 166-176`
**Issue:** The Cypher ends in `RETURN d` but the code does not read the result (no `.single()` / `.consume()`). For an auto-commit write this is harmless (the implicit transaction commits on context exit), but `RETURN d` does unnecessary work and signals intent (read-back) that never happens.
**Fix:** Drop `RETURN d` from the MERGE since the return value is discarded, matching the write-only style in `scripts/seed.py`.

### IN-02: `type="resume"` is hardcoded; `Document.type` supports `note`/`ats_field`

**File:** `core/parser/pdf.py:170`; `core/schemas/models.py:84`
**Issue:** Every parsed document is MERGEd with `type="resume"`. The model comment (`models.py:84`) lists `resume / note / ats_field` as valid types. This is acceptable for a PDF-resume-only phase but is an undocumented hardcode that will need to become a parameter when notes/ATS fields are ingested.
**Fix:** Promote to a `parse(pdf_path, *, doc_type: str = "resume")` parameter, or add a comment noting the phase-scoped hardcode.

### IN-03: Module-level `glob().next()` in test will raise `StopIteration` at import time if corpus is absent

**File:** `tests/test_parser_unit.py:17`
**Issue:** `_RESUME_PDF = next(Path("rnd/data/resume").glob("*.pdf"))` runs at module import. If the corpus directory is empty/missing (fresh clone, CI without R&D data), this raises `StopIteration` during *collection*, erroring the whole test module rather than skipping. The integration test handles this gracefully (`test_parser_integration.py:96-101` uses `pytest.skip`); the unit test does not. Inconsistent and brittle.
**Fix:** Resolve `_RESUME_PDF` inside a fixture (or guard with `pytest.skip`) so a missing corpus skips cleanly instead of erroring collection.

### IN-04: Relative `Path("rnd/data/resume")` couples tests to the invocation cwd

**File:** `tests/test_parser_unit.py:17`, `tests/test_parser_integration.py:25,41,67,95`
**Issue:** Tests reference the corpus via a cwd-relative path. Running `pytest` from any directory other than the repo root silently finds no PDFs (integration tests skip, unit test errors per IN-03). This makes the suite invocation-location-dependent.
**Fix:** Anchor to the repo root, e.g. `Path(__file__).resolve().parents[1] / "rnd" / "data" / "resume"`.

---

_Reviewed: 2026-06-11_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
