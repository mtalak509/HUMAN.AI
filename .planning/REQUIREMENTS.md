# Requirements: HUMAN.AI

**Defined:** 2026-06-03
**Milestone:** v1.1 — Ingestion Pipeline
**Core Value:** Загрузил PDF-резюме → кандидат появился в графе с experience, education, skills — без ручного ввода.

## v1.0 Requirements (выполнено)

### Инфраструктура

- [x] **INFRA-01**: GET /health возвращает 200 OK — Фаза 1
- [x] **INFRA-02**: Настройки читаются из .env через pydantic-settings — Фаза 1
- [x] **INFRA-03**: loguru, цветной вывод, LOG_JSON для прода — Фаза 1
- [x] **INFRA-04**: docker compose up -d поднимает весь стек — Фаза 1
- [x] **ONTO-01**: 12 Pydantic-моделей онтологии — Фаза 2
- [x] **ONTO-02**: Cypher-миграции, constraints и indexes — Фаза 2
- [x] **ONTO-03**: Async Neo4j driver, ping(), context-manager сессий — Фаза 1
- [x] **SEED-01**: scripts/seed.py — кандидат c-001 с полным графом — Фаза 3
- [x] **SEED-02**: scripts/queries.py — поиск по навыку/компании/статусу — Фаза 3
- [x] **TEST-01**: tests/conftest.py — session-scoped fixtures — Фаза 3
- [x] **TEST-02**: tests/test_infra.py — smoke-тесты Neo4j/Qdrant/Redis — Фаза 3

## v1.1 Requirements (активные)

### Парсер (PDF)

- [x] **PARSE-01**: Система принимает PDF-файл и извлекает plain text (pypdf-only за seam'ом; pdfplumber-каскад отложен — D-01) ✅ Фаза 4
- [x] **PARSE-02**: Система сохраняет исходный PDF и текст на диск (`{storage_root}/documents/{document_id}/`) ✅ Фаза 4
- [x] **PARSE-03**: Система создаёт `Document`-узел в Neo4j (file_uri, text_uri, parser_version, extraction_status, ingested_at) ✅ Фаза 4

### LLM-экстрактор

- [x] **EXTR-01**: Система принимает plain text и возвращает структурированный Resume-объект через LLM ✅ Фаза 5
- [x] **EXTR-02**: Режим json_object + Pydantic-валидация + 1 retry при ValidationError ✅ Фаза 5
- [x] **EXTR-03**: Schema охватывает: full_name, contacts, experiences (даты/компания/роль/навыки), education, skills

### Graph Writer

- [ ] **WRITE-01**: Graph Writer создаёт Candidate + все связанные узлы через MERGE
- [ ] **WRITE-02**: Graph Writer создаёт Fact-узлы с провенансом (ссылка на Document)
- [ ] **WRITE-03**: Денормализация: прямые связи Candidate→Skill для скорости поиска
- [ ] **WRITE-04**: Повторный запуск на том же документе не создаёт дублей

### API и Pipeline

- [ ] **API-01**: POST /documents принимает PDF, возвращает document_id и task_id
- [ ] **API-02**: GET /documents/{id} возвращает статус (queued/parsing/extracting/writing/written/failed)
- [ ] **PIPE-01**: Полный цикл parse→extract→write выполняется асинхронно через Celery

## v2 Requirements (отложено)

### Парсер (расширение)
- **PARSE-04**: DOCX-поддержка
- **PARSE-05**: OCR fallback для скан-PDF (tesseract)

### Entity Resolver
- **RESOLV-01**: Дедупликация кандидатов по email/телефону
- **RESOLV-02**: Нечёткий матч ФИО — только с ручным подтверждением

### Векторный слой
- **QDRANT-01**: Коллекции skills, companies, experiences, resumes в Qdrant
- **QDRANT-02**: BGE-M3 эмбеддинги локально на CPU

### Eval
- **EVAL-01**: 20 размеченных резюме, precision/recall по типам сущностей

## Вне скопа

| Feature | Причина |
|---------|---------|
| Полноценный R&D (30 резюме, 3 модели) | Smoke-test достаточно для старта |
| Eval baseline в v1.1 | Пропускаем — метрики на потом |
| DOCX, OCR в v1.1 | PDF достаточно; усложнение без нужды на старте |
| Entity Resolver в v1.1 | Каждое резюме = новый кандидат; дубли осознанно |
| KAG retrieval | v1.3 |
| Huntflow-коннектор | v1.2 |
| Фронтенд | v1.4 |
| 152-ФЗ, RBAC, мультитенантность | За пределами MVP |

## Трассировка (v1.1)

| Требование | Фаза | Статус |
|------------|------|--------|
| PARSE-01 | Фаза 4 | Done ✅ |
| PARSE-02 | Фаза 4 | Done ✅ |
| PARSE-03 | Фаза 4 | Done ✅ |
| EXTR-01 | Фаза 5 | Done ✅ 2026-06-11 |
| EXTR-02 | Фаза 5 | Done ✅ 2026-06-11 |
| EXTR-03 | Фаза 5 | Complete ✅ 2026-06-11 |
| WRITE-01 | Фаза 6 | Pending |
| WRITE-02 | Фаза 6 | Pending |
| WRITE-03 | Фаза 6 | Pending |
| WRITE-04 | Фаза 6 | Pending |
| API-01 | Фаза 7 | Pending |
| API-02 | Фаза 7 | Pending |
| PIPE-01 | Фаза 7 | Pending |

**Coverage:**
- v1.1 requirements: 13 total
- Mapped to phases: 13
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-03*
*Last updated: 2026-06-11 — EXTR-01/EXTR-02 complete (Phase 5 plan 05-02)*
