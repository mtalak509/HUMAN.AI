---
phase: 07-ingestion-api
reviewed: 2026-06-14T00:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - api/dependencies.py
  - api/main.py
  - api/routers/__init__.py
  - api/routers/documents.py
  - core/database/migrations.py
  - core/pipeline/__init__.py
  - core/pipeline/celery_app.py
  - core/pipeline/status.py
  - core/pipeline/tasks.py
  - core/schemas/models.py
  - tests/test_documents_api_unit.py
  - tests/test_ingestion_e2e.py
  - tests/test_pipeline_status_unit.py
  - tests/test_pipeline_task_unit.py
findings:
  critical: 1
  warning: 6
  info: 5
  total: 12
status: issues_found
---

# Phase 7: Code Review Report

**Reviewed:** 2026-06-14
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

Phase 7 wires the Celery ingestion pipeline (parse -> extract -> write) to two FastAPI endpoints (POST/GET /documents). The implementation is generally careful: bound Cypher params throughout, path-traversal guards, size caps, content-type validation, status-smart dedup, and graceful Neo4j degradation are all present and tested. Tests are thorough for the documented decisions.

However, there is one BLOCKER: a duplicate, non-DI definition of `get_db`/`get_settings` in `api/main.py` that diverges from `api/dependencies.py` and is silently dead — but it masks a real DI fragility that will surface the moment any caller imports the wrong symbol. More importantly, several correctness gaps exist around the failed-re-enqueue file-write ordering, partial reads consumed by the size check, and the `set_failed` path itself silently failing on a mid-pipeline Neo4j drop. Details below.

## Critical Issues

### CR-01: `set_failed` can itself raise on a mid-pipeline Neo4j outage, masking the original stage error and leaving the document stuck in `processing`

**File:** `core/pipeline/tasks.py:97-126`
**Issue:** Each stage wraps its work in `try/except` and calls `set_failed(s, ...)` inside `async with db.session()`. If Neo4j becomes unavailable *after* the initial `is_connected` check (line 64) but during a stage — a realistic failure mode, since parse/extract/write involve long-running I/O and LLM calls of up to 60s — then `db.session()` raises `RuntimeError` (see `FakeGraphDB.session` semantics and `GraphDB`), and that new exception replaces the original stage exception. The document is left permanently in `processing` (set at line 72) with no `failed` status, no `error`, and no `failed_stage`. The GET endpoint will report `processing` forever; the D-05 dedup logic (line 167) then refuses to re-enqueue it (`processing` -> 202 task_id=null), so the document is wedged with no operator recovery path short of manual Cypher.

This is a data-integrity/availability defect: the pipeline's core promise (T-07-03: "never a silent success-with-no-data state") has a symmetric hole on the failure side — a silent stuck-in-processing state.

**Fix:** Make the failure-recording best-effort and preserve the original exception:

```python
async def _record_failure(db, document_id, exc, stage):
    try:
        async with db.session() as s:
            await set_failed(s, document_id, str(exc)[:_MAX_ERROR_LEN], stage)
    except Exception as rec_exc:
        logger.error(
            "pipeline: could not record {} failure doc_id={} (neo4j down?): {}",
            stage, document_id, rec_exc,
        )

# in each stage:
except Exception as exc:
    await _record_failure(db, document_id, exc, "parse")
    logger.error("pipeline: parse FAILED doc_id={} error={}", document_id, exc)
    raise
```

Optionally, also reset `processing` -> `queued` (or a distinct `stuck` status) when failure recording fails, so dedup does not wedge the document.

## Warnings

### WR-01: Duplicate, divergent `get_db`/`get_settings` in `api/main.py` shadow the canonical DI helpers and are dead code that invites override-mismatch bugs

**File:** `api/main.py:62-67` (and `api/dependencies.py:24-31`)
**Issue:** `api/main.py` defines its own `get_settings`/`get_db` (lines 62-67), but the router (`api/routers/documents.py:30`) imports them from `api.dependencies`. Tests override `api.dependencies.get_db`. The `main.py` copies are used only by `/health` (line 73). This means there are two distinct function objects named `get_db`. If any future route or test imports `get_db` from `api.main` instead of `api.dependencies`, `app.dependency_overrides[get_db]` keyed on the other object silently fails to apply — the classic FastAPI DI footgun the `dependencies.py` module's own docstring (lines 3-5) was created to avoid. `/health` currently relies on the `main.py` copy, so overriding `api.dependencies.get_db` in a test would NOT affect `/health`.
**Fix:** Delete `api/main.py:62-67` and import the canonical helpers: `from api.dependencies import get_db, get_settings`. Use those in the `/health` route so a single object backs every override.

### WR-02: Size cap is enforced *after* the entire body is read into memory, defeating its stated purpose (T-07-06)

**File:** `api/routers/documents.py:127-137`
**Issue:** `data = await file.read()` (line 127) reads the full upload into RAM before line 133 checks `len(data) > MAX_UPLOAD_BYTES`. The comment at line 48 claims the cap "bounds memory/disk per request", but a 2 GiB upload is fully buffered in memory before rejection — the memory bound is not actually enforced. Starlette streams to a spooled temp file, so it is not unbounded heap, but it is unbounded disk and the comment overstates the protection.
**Fix:** Stream and short-circuit:

```python
data = bytearray()
async for chunk in file:  # or read in fixed-size chunks
    data.extend(chunk)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="...")
```

Or enforce a server/ingress-level body-size limit (uvicorn/proxy) as the primary control and document the in-handler check as defense-in-depth.

### WR-03: Failed-re-enqueue branch writes the PDF file *inside* the open Neo4j session, unlike the brand-new branch — and does the disk write before `reset_for_requeue`, so a write failure leaves a half-reset node

**File:** `api/routers/documents.py:177-193`
**Issue:** The brand-new path (lines 195-208) deliberately enqueues *after* `async with db.session()` closes (comment line 207). The failed-re-enqueue path (lines 181-193) instead does `mkdir`/`write_bytes` AND `process_document.delay()` *inside* the still-open session block. Two problems: (1) a slow/failing disk write holds the Neo4j session open longer than necessary; (2) ordering is `write_bytes` -> `reset_for_requeue` -> `delay` all in one block, but if `write_bytes` raises (disk full, permissions), the node is never reset and stays `failed` — recoverable, but inconsistent with the documented "files FIRST" discipline elsewhere. More subtly, `delay()` is called inside the session here but outside it in the new-doc branch — inconsistent transaction boundaries for the same logical operation.
**Fix:** Mirror the brand-new branch: perform the disk write and `reset_for_requeue` inside the session, then break out and call `process_document.delay()` after the session closes. Keep the two branches structurally identical.

### WR-04: `_run` re-derives the PDF path by globbing instead of reading the `file_uri` the API stored, so a re-POST with a different filename leaves a stale PDF and `glob()[0]` may pick the wrong one

**File:** `core/pipeline/tasks.py:79-86`
**Issue:** The API stores `file_uri` on the Document node (line 205 / `merge_document_queued`), but `_run` ignores it and does `list(pdf_dir.glob("*.pdf"))[0]` (lines 80, 86). Because `document_id` is the SHA-256 of the bytes, two uploads with identical bytes but different filenames (e.g. `resume.pdf` then `cv.pdf` on a failed re-enqueue, line 185) write *two* files into the same `documents/{id}/` directory. `glob` ordering is filesystem-dependent and unsorted, so `[0]` is non-deterministic. The bytes are identical so the parse result is the same — but the stale duplicate file accumulates and the "pick first" is a latent foot-gun if filename ever influences behavior. Reading the canonical `file_uri` would be both correct and one fewer source of truth.
**Fix:** Read `file_uri` from the node (the GET helper already MATCHes the Document) and resolve `settings.storage_root / file_uri`. If you keep the glob, sort and assert exactly one candidate, or overwrite rather than add files on re-POST (use the same `safe_name` deterministically, e.g. always store as `original.pdf`).

### WR-05: `merge_document_queued` uses `ON CREATE SET`, so a re-POST of a *failed* document never refreshes `file_uri`/`ingested_at`, and the brand-new dedup path cannot self-heal a node created without those fields

**File:** `core/pipeline/status.py:31-37`, `api/routers/documents.py:188-189`
**Issue:** `_MERGE_QUEUED_CYPHER` sets `processing_status`, `file_uri`, `ingested_at` only `ON CREATE`. The failed-re-enqueue branch calls `reset_for_requeue` (which sets status/error/failed_stage) but never updates `file_uri` or `ingested_at`. If the new upload has a different filename, the node's `file_uri` still points at the old name. Combined with WR-04 (glob ignores file_uri) this is currently masked, but if WR-04 is fixed to honor `file_uri`, the re-enqueue would parse the *old* file path. The `ON CREATE SET` comment (line 30) justifies this for not clobbering in-flight status, but `file_uri`/`ingested_at` are not status and arguably should refresh.
**Fix:** Have `reset_for_requeue` also `SET d.file_uri = $file_uri, d.ingested_at = $now`, or split the queued MERGE so status uses `ON CREATE SET` while `file_uri` uses plain `SET`.

### WR-06: Lifespan startup masks all migration/connection errors and can leave `app.state.db` in an inconsistent `is_connected` state

**File:** `api/main.py:33-41`
**Issue:** The `try` wraps both `connect_with_retry` and `apply_all`. If `apply_all()` raises (e.g. a malformed constraint, a Neo4j permissions error) *after* a successful connect, the `except` logs a warning and then the `hasattr` guard (line 39) does nothing because `is_connected` already exists and is `True`. The app then starts serving with `is_connected=True` but a half-applied/failed schema — POST /documents will pass the `is_connected` guard and MERGE against a DB whose constraints may be missing, risking duplicate Document nodes (no uniqueness enforced). The broad `except Exception` also swallows genuinely fatal misconfigurations into a warning.
**Fix:** Separate the two concerns: let `connect_with_retry` own degradation (it already sets `is_connected=False` on failure per CLAUDE.md), and let migration failures be logged distinctly. Do not assume `is_connected` is healthy just because connect did not raise.

## Info

### IN-01: `get_document` does not validate `document_id` shape before querying

**File:** `api/routers/documents.py:223-252`
**Issue:** `document_id` is taken verbatim from the path and used as a bound `$param` (safe from injection, T-07-09 holds). But there is no check that it is a 64-char hex string. Any garbage path segment hits Neo4j and returns 404 — harmless, but a cheap `len==64 and all-hex` validation would reject obvious garbage early and document the contract.
**Fix:** Add a lightweight format guard (regex `^[0-9a-f]{64}$`) returning 422 for malformed ids.

### IN-02: `error` truncation to 2000 chars can split a multibyte UTF-8 sequence

**File:** `core/pipeline/tasks.py:99,110,124`
**Issue:** `str(exc)[:_MAX_ERROR_LEN]` slices a Python `str` by code points (not bytes), so it will not corrupt UTF-8 at the Python level — but the comment at status.py:118 ("truncated to 2000 chars by caller") and the storage layer should be confirmed to handle the value as text. Low risk; noting for completeness since error text may contain Cyrillic (resumes are RU).
**Fix:** No change required; optionally append an ellipsis marker when truncated so consumers know the message was cut.

### IN-03: `create_document` `settings` param typed as `Any` instead of `Settings`

**File:** `api/routers/documents.py:97`
**Issue:** `settings: Any = Depends(get_settings)` loses type checking on `settings.storage_root`. The GET handler and the rest of the codebase use concrete types. `Any` here defeats mypy on a path-construction line (storage_root) that is security-relevant.
**Fix:** `from core.config import Settings` and annotate `settings: Settings = Depends(get_settings)`.

### IN-04: Magic literal `413` used instead of `status.HTTP_413_REQUEST_ENTITY_TOO_LARGE`

**File:** `api/routers/documents.py:135` and `92` (`status_code=202`)
**Issue:** Line 135 hardcodes `413` while every other status in the file uses the `status.HTTP_*` constants (lines 116, 130, 145). Line 92 uses bare `202`. Inconsistent style; the named constants are more grep-able and self-documenting.
**Fix:** Use `status.HTTP_413_REQUEST_ENTITY_TOO_LARGE` and `status.HTTP_202_ACCEPTED`.

### IN-05: Test mutates class-level `FakeSettings.storage_root`, creating cross-test ordering coupling

**File:** `tests/test_documents_api_unit.py:67,119,144,...`
**Issue:** `FakeSettings.storage_root` is a class attribute reassigned per-test to `tmp_path` (e.g. line 119). Tests that do not set it (e.g. `test_post_neo4j_down_returns_503`, GET tests) inherit whatever the previous test left — `Path("/tmp/test_storage")` or a stale `tmp_path`. Those tests happen not to write files, so it is currently benign, but it is order-dependent global mutation. The 503/GET tests would write to a leaked path if their code paths ever changed.
**Fix:** Set `storage_root` per-instance in `make_client`/`override_settings`, or use an instance attribute rather than mutating the class.

---

_Reviewed: 2026-06-14_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
