# Roadmap: HUMAN.AI — Milestone v1.1 Ingestion Pipeline

## Обзор

Milestone v1.1 — первый полный ingestion-пайплайн: PDF → парсер → LLM-экстрактор → Graph Writer → Neo4j. Цель: загрузить PDF-резюме через API и получить кандидата в графе с experience, education, skills — без ручного ввода.

Фундамент (Фазы 1–3, milestone v1.0) готов. Код LLM-экстрактора и парсера протестирован в R&D (`rnd/src/`). Этот milestone переводит R&D-наработки в продакшен-компоненты и добавляет Graph Writer + API.

**Критерий выхода из v1.1:** `POST /documents` с реальным PDF → через несколько секунд в Neo4j появился Candidate с полным графом связей (Skills, Experience, Education, Contacts, Facts). Запрос из `scripts/queries.py` находит нового кандидата.

**Нумерация фаз продолжается с 4** (milestone v1.0 завершился на Фазе 3).

## Фазы

- [x] **Фаза 4: PDF-парсер** — `core/parser/` с pypdf-извлечением (каскад на pdfplumber отложен — D-01), object storage, Document-узел в графе ✅ 2026-06-11
- [x] **Фаза 5: LLM-экстрактор** — `core/extractor/` на базе `rnd/src/`, адаптированный под полную онтологию ✅ 2026-06-11
- [ ] **Фаза 6: Graph Writer** — `core/writer/` — ExtractedFact[] → Cypher MERGE → Neo4j с Fact-провенансом
- [ ] **Фаза 7: Ingestion API** — `POST /documents`, `GET /documents/{id}`, Celery-task, сквозная интеграция

## Детали фаз

### Phase 4: PDF-парсер
**Goal:** Система принимает PDF, извлекает текст, сохраняет файл и создаёт Document-узел в Neo4j — всё через единый `PdfParser` класс в `core/parser/`
**Depends on:** Фаза 3 (Neo4j driver, Document Pydantic-модель)
**Requirements:** PARSE-01, PARSE-02, PARSE-03
**Success Criteria:**
  1. `PdfParser.parse(path)` возвращает объект с extracted_text, document_id, file_uri, text_uri
  2. Исходный PDF и текстовый файл сохранены в `/storage/documents/{document_id}/`
  3. `Document`-узел создан в Neo4j через MERGE с корректными полями
  4. На резюме из `rnd/data/resume/` — текст извлечён pypdf, никаких пустых страниц в логах (D-03: каскад на pdfplumber сужен до pypdf-only в v1)
  5. Повторный вызов с тем же PDF не создаёт дублей (идемпотентность по SHA-256)

**Plans:** 2 плана

Plans:
- [x] 04-01-PLAN.md — extraction-backend seam (Protocol+PyPdfBackend), SHA-256 document_id, object storage, storage_root setting, Wave 0 test stubs (Wave 1) ✅ 2026-06-11
- [x] 04-02-PLAN.md — Document-модель D-09 + идемпотентный Neo4j MERGE + интеграционные тесты PARSE-03 (Wave 2) ✅ 2026-06-11

### Phase 5: LLM-экстрактор
**Goal:** Система принимает plain text резюме и возвращает структурированные данные кандидата через LLM — перенос `rnd/src/openrouter_client.py` в `core/extractor/` с адаптацией под полную онтологию
**Depends on:** Фаза 4 (Document-узел, plain text)
**Requirements:** EXTR-01, EXTR-02, EXTR-03
**Success Criteria:**
  1. `Extractor.extract(text, document_id)` возвращает `ExtractedCandidate` — Pydantic-объект с полями из онтологии
  2. Режим json_object + Pydantic-валидация + 1 retry работает без изменений (перенесён из rnd/)
  3. Schema охватывает: full_name, contacts (email/phone/telegram/linkedin), experiences (from_date/to_date/company/role/description/skills_mentioned), education, skills
  4. На 5 резюме из `rnd/data/resume/` — 0 ValidationError, результаты совпадают с `rnd/data/results/*.parsed.json`
  5. `model_version` и `document_id` пишутся в каждый извлечённый факт

**Plans:** 2 плана

Plans:
- [x] 05-01-PLAN.md — `core/extractor/schema.py` (ExtractedCandidate + is_current + провенанс) + конфиг-кнобы экстрактора в Settings; equivalence-валидация 5 эталонных parsed.json (Wave 1) ✅ 2026-06-11
- [x] 05-02-PLAN.md — `core/extractor/llm.py` (Extractor: async extract + json_object + 1 retry + штамповка провенанса) + live equivalence integration-тест (Wave 2) ✅ 2026-06-11

### Phase 6: Graph Writer
**Goal:** Система принимает ExtractedCandidate и записывает полный граф кандидата в Neo4j через MERGE — с Fact-провенансом и денормализованными прямыми связями
**Depends on:** Фаза 5 (ExtractedCandidate), Фаза 4 (Document-узел)
**Requirements:** WRITE-01, WRITE-02, WRITE-03, WRITE-04
**Success Criteria:**
  1. `GraphWriter.write(candidate, document_id)` создаёт все узлы: Candidate, Contact, Skill, Experience, Company, Role, Education — через MERGE
  2. Для каждого извлечённого факта создан Fact-узел с `EXTRACTED_FROM → Document` и `SUPPORTS → Skill/Experience/...`
  3. Прямые связи `Candidate -[:HAS_SKILL]-> Skill` созданы параллельно с Fact-узлами (денормализация)
  4. Повторный `write()` с тем же документом — граф не изменился, узлов не прибавилось
  5. Cypher-запросы из `scripts/queries.py` находят нового кандидата по навыку и компании

**Plans:** 2 плана

Plans:
- [ ] 06-01: `core/writer/cypher.py` — Cypher MERGE транзакции для всех 12 типов узлов
- [ ] 06-02: `core/writer/graph_writer.py` — GraphWriter класс, Fact-провенанс, идемпотентность

### Phase 7: Ingestion API
**Goal:** Полный ingestion-пайплайн доступен через HTTP API — `POST /documents` запускает Celery-задачу, `GET /documents/{id}` отдаёт статус; сквозной тест: PDF через API → кандидат в графе
**Depends on:** Фазы 4–6 (парсер, экстрактор, writer)
**Requirements:** API-01, API-02, PIPE-01
**Success Criteria:**
  1. `POST /documents` (multipart/form-data, поле `file`) возвращает `{"document_id": "...", "task_id": "..."}` за < 200ms
  2. `GET /documents/{document_id}` возвращает корректный статус на каждом этапе (queued → parsing → extracting → writing → written)
  3. Celery worker обрабатывает PDF: parse → extract → write — без блокировки HTTP-сервера
  4. Сквозной тест: POST реального PDF → polling GET до `written` → запрос `find_candidates_by_skill()` находит кандидата
  5. При ошибке на любом шаге — статус `failed` с описанием ошибки, повторный POST не создаёт дублей

**Plans:** 3 плана

Plans:

**Wave 1** *(независимые)*
- [ ] 07-01: Celery task `process_document` — оркестрирует parse→extract→write, обновляет статус в Neo4j
- [ ] 07-02: API эндпоинты — `POST /documents`, `GET /documents/{id}` в `api/routers/documents.py`

**Wave 2** *(blocked on Wave 1)*
- [ ] 07-03: Сквозной интеграционный тест — PDF → API → Neo4j, smoke-тест пайплайна

## Прогресс

| Фаза | Планов выполнено | Статус | Завершена |
|------|-----------------|--------|-----------|
| 4. PDF-парсер | 2/2 | Complete | 2026-06-11 |
| 5. LLM-экстрактор | 2/2 | Complete | 2026-06-11 |
| 6. Graph Writer | 0/2 | Pending | — |
| 7. Ingestion API | 0/3 | Pending | — |
