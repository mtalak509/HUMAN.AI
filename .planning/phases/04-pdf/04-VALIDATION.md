---
phase: 4
slug: pdf
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-03
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (asyncio_mode=auto) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `pytest tests/test_parser_unit.py -x` |
| **Full suite command** | `pytest tests/ --cov=core/parser --cov-report=term-missing` |
| **Estimated runtime** | ~15 seconds (unit) / ~30 seconds (full, needs Neo4j) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_parser_unit.py -x`
- **After every plan wave:** Run `pytest tests/ -x --cov=core/parser --cov-report=term-missing`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-* | 01 | 1 | PARSE-01 | — | extract_text returns non-empty string from text-PDF | unit | `pytest tests/test_parser_unit.py::test_pypdf_backend_extracts_text -x` | ❌ W0 | ⬜ pending |
| 04-01-* | 01 | 1 | PARSE-01 | — | page markers `--- PAGE 1 ---` present | unit | `pytest tests/test_parser_unit.py::test_page_markers_format -x` | ❌ W0 | ⬜ pending |
| 04-01-* | 01 | 1 | PARSE-01 | — | image-only/all-empty PDF → status=empty, no crash | unit | `pytest tests/test_parser_unit.py::test_empty_pdf_graceful -x` | ❌ W0 | ⬜ pending |
| 04-01-* | 01 | 1 | PARSE-01 | — | extraction_status=ok for valid, empty for blank | unit | `pytest tests/test_parser_unit.py::test_extraction_status -x` | ❌ W0 | ⬜ pending |
| 04-01-* | 01 | 1 | PARSE-02 | — | PDF saved at /storage/documents/{id}/ | unit | `pytest tests/test_parser_unit.py::test_storage_layout -x` | ❌ W0 | ⬜ pending |
| 04-01-* | 01 | 1 | PARSE-02 | — | text.md saved at /storage/documents/{id}/ | unit | `pytest tests/test_parser_unit.py::test_text_md_saved -x` | ❌ W0 | ⬜ pending |
| 04-01-* | 01 | 1 | PARSE-02 | — | re-parse same PDF → same document_id (SHA-256) | unit | `pytest tests/test_parser_unit.py::test_sha256_idempotent -x` | ❌ W0 | ⬜ pending |
| 04-02-* | 02 | 2 | PARSE-03 | — | Document node exists in Neo4j after parse | integration | `pytest tests/test_parser_integration.py::test_document_node_created -x` | ❌ W0 | ⬜ pending |
| 04-02-* | 02 | 2 | PARSE-03 | — | re-parse → no duplicate Document node | integration | `pytest tests/test_parser_integration.py::test_document_node_idempotent -x` | ❌ W0 | ⬜ pending |
| 04-02-* | 02 | 2 | PARSE-03 | — | Document.text_uri/parser_version/extraction_status set | integration | `pytest tests/test_parser_integration.py::test_document_node_fields -x` | ❌ W0 | ⬜ pending |
| 04-02-* | 02 | 2 | PARSE-01+all | — | all 5 rnd/data/resume/ PDFs — no crash, non-empty text | integration | `pytest tests/test_parser_integration.py::test_rnd_corpus_smoke -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_parser_unit.py` — stubs for PARSE-01 (extraction), PARSE-02 (storage + SHA-256 idempotency); no infra, uses `tmp_path`
- [ ] `tests/test_parser_integration.py` — stubs for PARSE-03 (Neo4j MERGE); requires running Neo4j; uses session-scoped `neo4j_driver` from `conftest.py`
- [ ] `storage/` directory handling in tests — fixture using `tmp_path` (no writes to real `/storage`)

*No framework install gaps — pytest + pytest-asyncio already in pyproject.toml dev extras.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Cyrillic text fidelity in extracted .md | PARSE-01 | Visual check of multilingual extraction quality | Open `/storage/documents/{id}/text.md` from a rnd resume, confirm Cyrillic renders correctly |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
