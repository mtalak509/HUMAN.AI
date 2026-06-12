---
phase: 04-pdf
plan: 01
subsystem: parser
tags: [pypdf, pathlib, sha256, asyncio, protocol, pydantic-settings]

requires: []

provides:
  - "TextExtractorBackend Protocol + PyPdfBackend (pypdf-only, v1)"
  - "PdfParser async class: SHA-256 document_id, run_in_executor, storage writes"
  - "ParseResult frozen dataclass: document_id, extracted_text, file_uri, text_uri, extraction_status, parser_version"
  - "Settings.storage_root: Path field (default='storage', env STORAGE_ROOT)"
  - "Unit test suite (9 tests green); integration stubs (4 skipped for plan 04-02)"

affects:
  - "04-02 (Document-node MERGE needs PdfParser + ParseResult)"
  - "Phase 5+ (any consumer of core.parser public API)"

tech-stack:
  added:
    - "pypdf >= 4.2 (text extraction, already in pyproject.toml)"
    - "asyncio.run_in_executor (stdlib pattern)"
    - "hashlib.sha256 (stdlib)"
    - "dataclasses.dataclass(frozen=True)"
    - "typing.Protocol + runtime_checkable"
  patterns:
    - "Extraction backend seam: TextExtractorBackend Protocol for future pdfplumber/OCR drop-in"
    - "Deterministic SHA-256 document_id from raw PDF bytes"
    - "run_in_executor offloads sync pypdf to thread pool"
    - "Sanitized filename via Path(pdf_path.name).name (T-04-02)"
    - "Relative storage URIs: documents/{id}/{filename}"

key-files:
  created:
    - "core/parser/_backend.py — TextExtractorBackend Protocol + PyPdfBackend"
    - "core/parser/pdf.py — PdfParser + ParseResult"
    - "core/parser/__init__.py — public re-export shim"
    - "tests/test_parser_unit.py — 9 unit tests (PARSE-01, PARSE-02, SHA-256)"
    - "tests/test_parser_integration.py — 4 stubs (skipped, plan 04-02)"
  modified:
    - "core/config.py — added storage_root: Path, openrouter_api_key: str | None"

key-decisions:
  - "PyPdfBackend returns ('', 'empty') when ALL pages are empty — no page markers in that case"
  - "openrouter_api_key added as optional field to Settings to accept pre-existing .env value"
  - "storage_root defaults to Path('storage'), overridable via STORAGE_ROOT env var"
  - "ParseResult.file_uri and text_uri are relative (not absolute) for portability"

patterns-established:
  - "core/parser/_backend.py: Protocol seam pattern for backend extensibility"
  - "core/parser/pdf.py: async service with run_in_executor for sync I/O"
  - "PdfParser constructor injection: db=None, storage_root=None, backend=None with get_settings() fallback"

requirements-completed: [PARSE-01, PARSE-02]

duration: 35min
completed: 2026-06-11
---

# Phase 4 Plan 01: PDF Parser — Extraction + Storage Layer Summary

**pypdf-backed text extractor behind TextExtractorBackend Protocol seam + async PdfParser with SHA-256 document_id, run_in_executor offload, and storage writes to {storage_root}/documents/{id}/**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-06-11T14:30:00Z
- **Completed:** 2026-06-11T15:09:00Z
- **Tasks:** 4 (Task 0 + Tasks 1-3)
- **Files modified/created:** 7

## Accomplishments

- `TextExtractorBackend` Protocol (runtime_checkable) и `PyPdfBackend` с маркерами `--- PAGE i ---`, логированием пустых страниц и статусом "empty" для all-blank PDF
- `PdfParser.parse()`: async, SHA-256 document_id (64 hex), run_in_executor, sanitized filename, сохраняет оригинальный PDF + text.md в `{storage_root}/documents/{id}/`
- `Settings.storage_root` — новое поле Path с дефолтом `storage`, переопределяется через `STORAGE_ROOT`
- 9/9 unit тестов зелёных; 4 integration стаба пропускаются (план 04-02)

## Task Commits

1. **Task 0: Test scaffolds (Wave 0 RED)** — `e4aa5ca` (test)
2. **Task 1: Settings.storage_root** — `8d2e5d0` (feat)
3. **Task 2: TextExtractorBackend + PyPdfBackend** — `7637aba` (feat)
4. **Task 3: PdfParser + ParseResult + __init__** — `70c32d9` (feat)

## Files Created/Modified

- `core/parser/_backend.py` — TextExtractorBackend Protocol + PyPdfBackend (pypdf extraction seam)
- `core/parser/pdf.py` — PdfParser async service + ParseResult frozen dataclass
- `core/parser/__init__.py` — re-export shim: `PdfParser`, `ParseResult`
- `core/config.py` — добавлен `storage_root: Path`, `openrouter_api_key: str | None`
- `tests/test_parser_unit.py` — 9 unit тестов (PARSE-01, PARSE-02, SHA-256 idempotency)
- `tests/test_parser_integration.py` — 4 заглушки с `@pytest.mark.skip` для плана 04-02

## Decisions Made

- `PyPdfBackend` возвращает `("", "empty")` когда ВСЕ страницы пустые — маркеры не включаются. Это явно удовлетворяет контракту "Image-only PDF returns ('', 'empty') without raising"
- `openrouter_api_key: str | None = None` добавлен в Settings как опциональное поле: ключ уже присутствует в `.env` проекта для R&D-скриптов, его отсутствие в Settings вызывало `ValidationError: Extra inputs are not permitted`
- `storage_root` по умолчанию `Path("storage")` (относительный путь), переопределяется через env `STORAGE_ROOT`
- `ParseResult.file_uri` и `text_uri` — относительные пути (не абсолютные) для переносимости между окружениями

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] PyPdfBackend возвращал ('--- PAGE 1 ---\n', 'ok') для blank PDF вместо ('', 'empty')**
- **Found during:** Task 3 (запуск unit тестов, `test_empty_pdf_graceful`)
- **Issue:** `text.strip()` на строке `'--- PAGE 1 ---\n'` давал непустую строку → статус оставался "ok"; тест ожидал `text == ""`, `status == "empty"`
- **Fix:** Добавлена проверка `all_empty = len(empty_pages) == len(pages)` — если все страницы пустые, сразу возвращается `("", "empty")` без page-markers
- **Files modified:** `core/parser/_backend.py`
- **Verification:** `test_empty_pdf_graceful` зелёный; все 9 unit тестов зелёные
- **Committed in:** `70c32d9` (Task 3 commit)

**2. [Rule 2 - Missing Critical] `openrouter_api_key` не объявлен в Settings — `get_settings()` падал с ValidationError**
- **Found during:** Task 1 (верификация `get_settings().storage_root`)
- **Issue:** `.env` содержит `OPENROUTER_API_KEY`, которое pydantic-settings пытается отдать в Settings, но `model_config` не разрешает extra fields → `ValidationError: Extra inputs are not permitted`
- **Fix:** Добавлено `openrouter_api_key: str | None = Field(default=None, ...)` в класс Settings
- **Files modified:** `core/config.py`
- **Verification:** `get_settings().storage_root` возвращает `Path('storage')` без ошибок
- **Committed in:** `8d2e5d0` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 Rule 1 — Bug, 1 Rule 2 — Missing Critical)
**Impact on plan:** Оба fix необходимы для корректности. Scope не расширен.

## Issues Encountered

- `tests/test_parser_unit.py` не мог запустить тесты бэкенда отдельно, так как `from core.parser import PdfParser` в начале файла фейлил до Task 3 — это ожидаемое RED-состояние TDD; тесты верифицировались полным запуском после Task 3

## Known Stubs

Нет. Все публичные API реализованы. Document-node MERGE намеренно не реализован (план 04-02) — это не стаб, а явный scope boundary.

## Next Phase Readiness

- `core.parser` готов к использованию в плане 04-02 (Document-node MERGE)
- `PdfParser(db=None, storage_root=...)` принимает `db` параметр для план 04-02 без изменения сигнатуры
- Закомментированный шаблон MERGE Cypher присутствует в `pdf.py` для ориентира
- `Settings.storage_root` доступен для всех upstream потребителей

---
*Phase: 04-pdf*
*Completed: 2026-06-11*
