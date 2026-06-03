# Phase 4: PDF-парсер - Context

**Gathered:** 2026-06-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Система принимает PDF, извлекает plain text, сохраняет оригинал + текст на диск и создаёт `Document`-узел в Neo4j — всё через единый `PdfParser` класс в `core/parser/`. Идемпотентно по содержимому файла.

В границах: извлечение текста (pypdf), object storage, Document-узел, идемпотентность.
Вне границ: LLM-экстракция (Фаза 5), Graph Writer кандидата (Фаза 6), API/Celery (Фаза 7), DOCX (PARSE-04), OCR (PARSE-05).

</domain>

<decisions>
## Implementation Decisions

### Извлечение текста / каскад
- **D-01:** v1 использует **только pypdf**. Каскад на pdfplumber **откладывается** — критерии срабатывания фолбэка пока неясны, писать его сейчас = гадание.
- **D-02:** Заложить **чистый шов (seam)** для backend'а извлечения — абстракция/стратегия, чтобы pdfplumber (или другой extractor) вставился позже без переписывания `PdfParser`. Шов обязателен, реализация фолбэка — нет.
- **D-03:** ⚠️ Это **сужает Success Criteria #4 роадмапа** (формулировка «pypdf→pdfplumber каскад»). При планировании трактовать критерий как «текст извлечён pypdf, пустых страниц в логах нет»; собственно каскад — отдельная будущая работа.

### Формат сохранённого текста
- **D-04:** Извлечённый текст сохраняется в формате **`.md`** (не `.txt`).
- **D-05:** **Page-маркеры сохраняются** — стиль `--- PAGE i ---` как в `rnd/src/pdf_parser.py`. Экстрактор Фазы 5 уже ел этот формат в smoke-test (0 ошибок) — не ломаем.
- **D-06:** `text_uri` на Document-узле указывает на `.md`-файл.

### Обработка пустого извлечения (скан/image-only PDF)
- **D-07:** При пустом извлечении (OCR вне скопа) — **не падать**. Сохранить исходный PDF, создать Document-узел, текст пустой.
- **D-08:** На Document пишется флаг **`extraction_status`** (напр. `ok` / `empty`). Согласуется с graceful-философией проекта; OCR позже сможет добить такие документы, они уже видны в графе.

### Document-модель (следствие решений)
- **D-09:** Pydantic-модель `core/schemas/models.py::Document` расширяется новыми полями: `text_uri`, `parser_version`, `extraction_status` (сейчас в модели только `id, type, file_uri, ingested_at, created_at`). Точный набор/типы — задача планировщика.

### Claude's Discretion
- **document_id = SHA-256(pdf_bytes)** — детерминированный id даёт идемпотентность напрямую через `MERGE (d:Document {id})`, без отдельного поля `sha256` и без dedup-запроса. (Зона не выбрана для обсуждения — решение за Claude, при планировании можно пересмотреть.)
- Storage-раскладка внутри `/storage/documents/{document_id}/` (имена файлов, сохранение исходного имени) и формат URI (относительные/абсолютные) — на усмотрение планировщика, разумные дефолты.
- Sync vs async интерфейс `PdfParser.parse()` — на усмотрение планировщика (запись в Neo4j через `GraphDB.session()` асинхронна).
- Точный синтаксис page-маркера в `.md` (оставить `--- PAGE i ---` или поднять до `## PAGE i`) — дефолт: сохранить существующий стиль.

</decisions>

<specifics>
## Specific Ideas

- «Fallback пока пропустим, оставим заглушку — писать его сейчас это тыкать в небо пальцем». Шов есть, реализации нет.
- «Уйти от txt к .md формату и сохранять page-маркеры».

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Архитектура и решения проекта
- `core_architecture.md` — общая архитектура, ingestion-пайплайн, роль Document/Fact-узлов
- `CLAUDE.md` — ключевые решения: MERGE-ключи = констрейнты, graceful degradation, скрипты используют прямой `get_settings()`, Fact-провенанс

### Граф и модели (вход Фазы 4)
- `core/schemas/models.py` §`class Document` — текущая Pydantic-модель Document (расширяется в D-09)
- `core/database/migrations.py` §`document_id_unique` — констрейнт `Document.id IS UNIQUE` (MERGE-ключ)
- `core/database/graph.py` §`GraphDB.session()` — async-интерфейс записи в Neo4j

### Задел из R&D
- `rnd/src/pdf_parser.py` — `pdf_to_text()` на pypdf, page-маркеры `--- PAGE i ---`, логирование пустых страниц (база для D-01/D-05)
- `rnd/smoke_test_findings.md` — почему формат текста важен для экстрактора Фазы 5

### Roadmap / требования
- `.planning/ROADMAP.md` §Phase 4 — Goal, Success Criteria (см. D-03 по критерию #4)
- `.planning/REQUIREMENTS.md` — PARSE-01, PARSE-02, PARSE-03

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `rnd/src/pdf_parser.py::pdf_to_text()` — готовая логика pypdf + page-маркеры + детект пустых страниц. Переносится в `core/parser/` как основа backend'а извлечения.
- `GraphDB.session()` (`core/database/graph.py`) — async-контекст для MERGE Document-узла.
- Паттерн скриптов: прямой `get_settings()` из `core/config.py` (lru_cache'd), не FastAPI DI.

### Established Patterns
- **MERGE-ключи = констрейнты.** Document MERGE-ится **только** по `.id` (констрейнт `document_id_unique`). document_id = SHA-256 → идемпотентность.
- **Graceful degradation.** Если Neo4j недоступен — не хардкрэшить (см. CLAUDE.md). Поведение парсера при недоступном графе уточнить при планировании, но философия — мягкая деградация.
- **Loguru** для логов; пустые страницы логируются (как в rnd-коде).

### Integration Points
- Вход: путь к PDF (позже — байты из API-загрузки Фазы 7).
- Выход вниз по пайплайну: `.md` с текстом (вход экстрактора Фазы 5), Document-узел с `document_id` (привязка Fact-провенанса в Фазе 6).
- Расширение модели `core/schemas/models.py::Document` затрагивает re-export shim `core/models.py`.

</code_context>

<deferred>
## Deferred Ideas

- **pdfplumber-фолбэк (каскад извлечения)** — реализация отложена (D-01). Шов под него закладывается сейчас (D-02), сама логика и критерии срабатывания — будущая работа. Связано с PARSE-04/PARSE-05 (DOCX/OCR) как семейство «улучшения извлечения».
- **OCR для скан-PDF** (PARSE-05) — вне v1.1; документы с `extraction_status=empty` (D-08) станут кандидатами на OCR-добор позже.

</deferred>

---

*Phase: 04-pdf*
*Context gathered: 2026-06-03*
