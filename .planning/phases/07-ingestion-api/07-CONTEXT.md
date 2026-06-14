# Phase 7: Ingestion API - Context

**Gathered:** 2026-06-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Expose the full ingestion pipeline over HTTP + Celery:

- **`POST /documents`** (multipart/form-data, поле `file`) — принимает PDF, возвращает
  `{document_id, task_id}` за < 200ms (API-01).
- **`GET /documents/{document_id}`** — возвращает текущий статус обработки (API-02).
- **Celery-таск `process_document`** — асинхронно оркеструет уже готовые компоненты:
  `PdfParser.parse → Extractor.extract → GraphWriter.write` (PIPE-01).

Покрывает требования **API-01, API-02, PIPE-01**.

**Вне границы (другие фазы / вне скопа v1.1):** retrieval (`POST /search` — v1.3),
entity resolution / дедуп между разными документами (v1.2), DOCX/OCR, аутентификация/RBAC,
фронтенд. Все три компонента пайплайна (parser/extractor/writer) уже реализованы и
протестированы в фазах 4–6 — эта фаза их **только связывает**, не переписывает.

</domain>

<decisions>
## Implementation Decisions

### Статус-трекинг (API-02)
- **D-01:** Набор статусов пайплайна — **минимальный**: `queued → processing → written`
  плюс `failed`. БЕЗ пер-этапных `parsing/extracting/writing` и БЕЗ `resolving`
  (entity resolver отложен в v1.2). `processing` — единый статус на всё время работы таска.
- **D-02:** ⚠️ **Осознанное отклонение от ROADMAP success criterion #2** (которое требует
  «GET возвращает статус на каждом этапе queued→parsing→extracting→writing→written»).
  Пер-этапная гранулярность сознательно убрана из основного статуса; диагностика «где упало»
  переносится в поле `failed_stage` (D-06), которое заполняется только при ошибке.
  **Планировщик должен скорректировать критерий проверки фазы под D-01.**
- **D-03:** Статус хранится **на узле `Document` в Neo4j** (новое поле, напр.
  `processing_status` — имя на усмотрение планировщика, но НЕ путать с существующим
  `extraction_status` "ok"/"empty" от парсера). Источник истины — Neo4j, НЕ Celery result
  backend / Redis (архитектура §5.7: «состояние полностью в Neo4j, нет in-memory state
  между шагами»).
- **D-04:** Узел `Document{id, status:queued}` создаётся **синхронно в обработчике POST**
  (через `MERGE`) ДО постановки таска в очередь. Гарантирует, что `GET` сразу после `POST`
  видит узел (нет окна гонки → нет 404 на `queued`).

### Дубликаты (success criterion #5)
- **D-05:** Повторный POST того же PDF (`document_id` детерминирован = SHA-256 байтов) —
  **умная обработка по текущему статусу существующего Document**:
  - `written` → вернуть существующий `document_id` без перезапуска таска (экономия
    платных LLM-вызовов; граф уже идемпотентен по WRITE-04, повторная экстракция — пустая
    трата денег).
  - `failed` → перезапустить обработку (новый таск).
  - `queued` / `processing` → вернуть текущий статус без дублирующего enqueue.
  - HTTP-код для случая «уже `written`» — на усмотрение планировщика (вероятно `200`
    с `task_id: null`); код для свежепринятого — `202 Accepted`.

### Ошибки и ретраи
- **D-06:** При падении — два поля на узле `Document`: `error` (текст исключения) и
  `failed_stage` (`parse` | `extract` | `write`). `GET` возвращает оба. Это компенсирует
  минимальный набор статусов (D-01): по `failed_stage` видно, на каком шаге упало.
- **D-07:** **Fail-fast, без авторетрая на уровне Celery-таска.** Любая ошибка →
  `status=failed` немедленно. Перезапуск — только вручную повторным POST (согласовано с
  D-05: `failed→перезапустить`). Внутренний 1-retry экстрактора на `ValidationError`
  (фаза 5, EXTR-02) сохраняется — это не уровень таска.

### Claude's Discretion (на усмотрение планировщика/исполнителя)
- **POST flow / document_id (область не выбрана пользователем — решено вытекающе из D-04):**
  обработчик POST: читает байты загрузки → вычисляет `document_id = SHA-256(bytes)` →
  сохраняет сырой файл в storage → `MERGE Document(queued)` → `process_document.delay(document_id)`
  → возвращает `{document_id, task_id}`. Celery-таск перечитывает файл по пути из storage
  (а не получает байты через брокер). Синхронная часть должна укладываться в < 200ms
  (резюме ~300 шт, PDF мелкие — SHA + один MERGE дёшевы).
  - Открытый под-вопрос планировщику: парсер сейчас сам вычисляет `document_id` и сам
    сохраняет файл внутри `parse()`. Нужно решить, как избежать двойного сохранения/
    двойного SHA — варианты: (а) POST сохраняет во временный путь, таск передаёт его в
    `parser.parse(path)` (парсер пере-сохранит под `document_id` — допустимо, идемпотентно);
    (б) лёгкий рефактор парсера, чтобы принимать заранее вычисленный `document_id`.
    Выбор за планировщиком; не ломать единый entry-point `PdfParser.parse`.
- Точное имя нового поля статуса на `Document` (`processing_status` рекомендовано).
- Нужен ли индекс на поле статуса в `migrations.py` (для возможных будущих list-запросов
  «все failed») — на усмотрение; в v1.1 не критично.
- Способ запуска async-кода (`parse/extract/write` — все `async`) внутри синхронного
  Celery-таска: `asyncio.run(...)` на таск vs общий loop. Следовать паттерну проекта
  (`run_in_executor` уже используется в parser/extractor для обратного — sync в async).
- Как именно `process_document` получает свой `GraphDB` (Celery-воркер вне FastAPI
  lifespan): фаза 6 заложила конструктор `GraphWriter(db=...)` без FastAPI DI — таск создаёт
  собственный `GraphDB` из `get_settings()` (паттерн скриптов, см. CLAUDE.md «Scripts use
  direct imports, not FastAPI DI»). Где открывать/закрывать драйвер (на таск vs на воркер) —
  на усмотрение планировщика.

</decisions>

<specifics>
## Specific Ideas

- ⚠️ **Neo4j-недоступность ≠ graceful degradation для этой фазы.** Парсер/писатель
  деградируют молча (лог-warning, без краха) при недоступном Neo4j — но в пайплайне статус
  ТОЖЕ пишется в Neo4j. Если граф недоступен, таск не может ни записать данные, ни обновить
  статус. Для фазы 7 это должно быть **`failed`** (или таск не должен молча «успешно»
  завершаться без записи). Планировщик должен явно обработать этот случай — не наследовать
  немой degradation парсера для шага write.
- `api/main.py` уже задаёт паттерн DI: `app.state.db` / `app.state.settings`,
  `Depends(get_db)` / `Depends(get_settings)`. Новые эндпоинты `POST/GET /documents`
  следуют ему (вероятно в `api/routers/documents.py`).
- `redis_url` уже в Settings — это и брокер, и (опционально) result backend Celery. Но по
  D-03 result backend НЕ источник истины статуса.
- Критерий успеха #4: после `written` запрос `scripts/queries.py::find_candidates_by_skill()`
  должен находить нового кандидата — это сквозной smoke-тест (план 07-03).

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Контракт API и async-пайплайн (главное)
- `docs/core_architecture.md` §5.7 (стр. 259–270) — async pipeline: контракт
  `POST /documents` → `{document_id, task_id}`, `GET /documents/{id}` → статус, Celery+Redis,
  «состояние полностью в Neo4j, нет in-memory state между шагами», «одна идемпотентная
  операция на шаг». **Источник истины по D-01…D-04.**
- `docs/core_architecture.md` §5.4 (стр. 214–221) — «одна транзакция на документ; если падает —
  откат целиком, документ остаётся в очереди на повтор» (соотнести с fail-fast D-07).
- `.planning/ROADMAP.md` — Phase 7 Success Criteria (#1–#5) + разбивка на 3 плана
  (07-01 Celery-task, 07-02 эндпоинты, 07-03 сквозной тест). Учесть отклонение D-02.

### Компоненты пайплайна (входы/выходы — НЕ переписывать)
- `core/parser/pdf.py` — `PdfParser.parse(pdf_path: Path) -> ParseResult` (async); сам
  вычисляет `document_id = SHA-256`, сохраняет PDF + `text.md`, MERGE'ит Document. См.
  под-вопрос в Claude's Discretion про двойное сохранение.
- `core/extractor/llm.py` — `Extractor.extract(text: str, document_id: str) -> ExtractedCandidate`
  (async, json_object + 1 retry, штампует провенанс).
- `core/writer/graph_writer.py` — `GraphWriter.write(candidate, document_id) -> None` (async,
  одна транзакция, конструктор `__init__(db=...)` без FastAPI DI — спроектирован под этот таск).

### Схема и инфраструктура
- `core/schemas/models.py` — модель `Document` (стр. 82–91); сейчас поля
  `extraction_status`/`parser_version`/`text_uri`. **Нужны новые поля:** статус пайплайна
  (D-03), `error` + `failed_stage` (D-06).
- `core/database/migrations.py` — `CONSTRAINTS`/`INDEXES`, единственный источник истины по
  схеме; сюда же возможный индекс на поле статуса (Claude's Discretion).
- `core/database/graph.py` — `GraphDB` (`is_connected`, `session()`, `execute_write`).
- `core/config.py` — `Settings`: `redis_url` (брокер Celery), `neo4j_*`, `openrouter_*`.
- `api/main.py` — lifespan, `app.state`, `get_db`/`get_settings` DI-паттерн для новых роутеров.
- `scripts/queries.py` — `find_candidates_by_skill/company/status` (критерий #4, сквозной тест).

### Конвенции
- `CLAUDE.md` — разделы «DI via app.state», «Scripts use direct imports, not FastAPI DI»
  (паттерн для Celery-таска), «GraphDB graceful degradation» (но см. оговорку в Specifics),
  «Settings are cached».

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Все три компонента пайплайна готовы и протестированы (фазы 4–6) — таск только вызывает
  их по очереди. Никакой бизнес-логики экстракции/записи в фазе 7 быть не должно.
- `api/main.py` lifespan + DI — образец для подключения роутеров и зависимостей.
- `core/config.py::Settings.redis_url` — готовый коннект для брокера Celery.
- `celery[redis]>=5.4` уже в зависимостях (`pyproject.toml`) — Celery не нужно добавлять.

### Established Patterns
- DI через `app.state` + `Depends` в API; скрипты/таски — прямой `get_settings()`
  (Celery-воркер вне FastAPI lifespan → паттерн скриптов).
- Идемпотентность через `MERGE` + `SET` (фазы 4/6) — применить к Document(status) апдейтам.
- `run_in_executor` для sync-кода в async (парсер/экстрактор) — обратная задача (async в
  sync Celery-таске) решается планировщиком.

### Integration Points
- Вход: HTTP multipart upload → storage (сырой PDF).
- Оркестрация: `process_document(document_id)` → parse → extract → write, обновляя
  `Document.status` после каждого шага (processing → written), при ошибке → failed +
  error + failed_stage.
- Document-узел: создан синхронно в POST (queued), затем дополняется парсером (file_uri,
  text_uri, extraction_status) и таском (статус). MERGE по `Document.id` — единый ключ.
- Выход/проверка: `scripts/queries.py` находит кандидата после `written`.

</code_context>

<deferred>
## Deferred Ideas

- **Пер-этапные статусы** (`parsing/extracting/writing`) — если понадобится тонкая
  наблюдаемость прогресса; в v1.1 заменены минимальным набором + `failed_stage` (D-01/D-06).
- **Celery autoretry** транзиентных ошибок (network/timeout, backoff) — отложено в пользу
  fail-fast (D-07); вернуться, если ручной перезапуск окажется болезненным на корпусе.
- **`POST /search` (retrieval-эндпоинт)** — milestone v1.3 (KAG), §5.5–5.6 архитектуры.
- **Entity resolution / дедуп между РАЗНЫМИ документами одного человека** — v1.2 (наследие
  D-08 фазы 6).
- **Bulk-загрузка / батч-эндпоинт** для первичной заливки ~300 резюме — не в v1.1, при
  необходимости отдельной фазой.

</deferred>

---

*Phase: 07-ingestion-api*
*Context gathered: 2026-06-14*
