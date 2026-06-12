# HUMAN.AI — Talent Intelligence Platform

## Что это такое

Backend-ядро Talent Intelligence Platform: пайплайн, который превращает PDF-резюме в графовую память компании (Neo4j), и retrieval-слой, который по запросу на естественном языке возвращает обоснованный шортлист кандидатов.

Целевой пилот: 1 клиент, ~300 резюме, 1 рекрутер, SaaS на нашей инфре.

## Ключевая ценность

Загрузил PDF-резюме → кандидат появился в графе с experience, education, skills — без ручного ввода.

## Текущий Milestone: v1.1 — Ingestion Pipeline

**Цель:** Первый полный ingestion-пайплайн: PDF → LLM-экстрактор → Neo4j-граф через API.

**Target features:**
- PDF-парсер на базе `rnd/src/pdf_parser.py` (pypdf → pdfplumber cascade)
- LLM-экстрактор v1 на базе `rnd/src/openrouter_client.py` (json_object + Pydantic + 1 retry)
- Graph Writer: ExtractedFact[] → Cypher MERGE → Neo4j с Fact-провенансом
- `POST /documents` API + Celery async pipeline

## Требования

### Проверенные (v1.0)

- ✓ Docker Compose с Neo4j 5.x, Qdrant, Redis, FastAPI — v1.0/Фаза 1
- ✓ 12 Pydantic-моделей онтологии (Candidate, Skill, Experience, Role, Company, Education, Vacancy, Status, HRNote, Document, Fact) — v1.0/Фаза 2
- ✓ Cypher-миграции: constraints и indexes — v1.0/Фаза 2
- ✓ Seed-кандидат c-001, `scripts/queries.py`, smoke-тесты — v1.0/Фаза 3
- ✓ PDF → plain text через pypdf, text-only LLM-экстракция, Pydantic Resume-схема — R&D smoke-test

### Активные (v1.1)

- [ ] PARSE-01: Парсер принимает PDF, извлекает текст через pypdf (fallback: pdfplumber)
- [ ] PARSE-02: Парсер сохраняет исходный PDF и текст на диск (`/storage/documents/{id}/`)
- [ ] PARSE-03: Парсер создаёт `Document`-узел в Neo4j (file_uri, text_uri, parser_version, ingested_at)
- [ ] EXTR-01: Экстрактор получает plain text, возвращает структурированный `Resume` через LLM
- [ ] EXTR-02: Экстрактор работает в режиме json_object + Pydantic-валидация + 1 retry
- [ ] EXTR-03: Extraction schema покрывает full_name, contacts, experiences, education, skills
- [ ] WRITE-01: Graph Writer создаёт Candidate + все связанные узлы через MERGE
- [ ] WRITE-02: Graph Writer создаёт Fact-узлы с провенансом (ссылка на Document)
- [ ] WRITE-03: Graph Writer денормализует прямые связи Candidate→Skill для скорости поиска
- [ ] WRITE-04: Запись в граф идемпотентна (повторный запуск не создаёт дублей)
- [ ] API-01: POST /documents принимает PDF-файл, возвращает document_id и task_id
- [ ] API-02: GET /documents/{id} возвращает статус обработки (queued/parsing/extracting/writing/written/failed)
- [ ] PIPE-01: Обработка документа выполняется асинхронно через Celery worker

### Вне скопа

- DOCX, OCR (tesseract) — после MVP, парсим только PDF
- Eval baseline (precision/recall на 20 резюме) — пропускаем
- Entity Resolver (дедупликация кандидатов) — Фаза 2 / milestone v1.2
- Qdrant-коллекции и эмбеддинги — milestone v1.2
- KAG retrieval — milestone v1.3
- Huntflow-коннектор — milestone v1.2
- Фронтенд — milestone v1.4
- 152-ФЗ, RBAC, мультитенантность — за пределами MVP

## Контекст

Стек: Python 3.11+, FastAPI, Neo4j 5.x, Qdrant, Celery + Redis, BGE-M3, Docker Compose.

**R&D smoke-test (2026-05-15, закрыт зелёным):** PyPDF2/pypdf + text-only LLM (Qwen3 через OpenRouter) на 5 резюме — 0 фактических ошибок, 0 галлюцинаций. Дефолт: `json_object` + Pydantic + 1 retry. Код в `rnd/src/` — переносится без изменений в продакшен.

**Полноценный R&D (30 резюме, 3 модели) пропущен** — smoke-test достаточно для продакшен-старта.

LLM-провайдер зафиксирован для старта: OpenRouter (Qwen3). Пересмотр по результатам Г1/Г4 после первых 50+ резюме.

## Ограничения

- **Стек**: Python 3.11+, FastAPI, Neo4j 5.x — изменение требует пересмотра архитектуры
- **PDF only**: DOCX и OCR — вне скопа v1.1
- **Бюджет**: инфра-расходы минимизированы — Docker Compose на одной VM
- **Онтология**: расширение — по факту боли, не раньше; Fact-узел обязателен

## Ключевые решения

| Решение | Обоснование | Результат |
|---------|-------------|-----------|
| Граф — источник правды, Qdrant — индекс | Вектор находит, граф объясняет; KAG-паттерн | ✓ Подтверждено |
| Fact как отдельный узел | Провенанс, версионность, конфликты из коробки | ✓ Подтверждено |
| BGE-M3 локально на CPU | Мультиязычность, ru-качество, нет зависимости от API | — Pending |
| Celery + Redis (не Airflow) | Минимальный стек, расширяется до Airflow позже | — Pending |
| Никаких строк вместо узлов | `Skill: "Python"` — это узел, иначе нормализация невозможна | ✓ Подтверждено |
| json_object + Pydantic + 1 retry (не json_schema) | Smoke-test: 0 ошибок vs 2/5 у json_schema; системная неполнота skills у json_schema | ✓ Подтверждено |
| PDF only для парсера v1 | pypdf справился со всеми 5 резюме в smoke-test; DOCX и OCR усложняют без нужды на старте | ✓ Принято |
| Entity Resolver — не в v1.1 | Каждое резюме = новый кандидат; дубли осознанно; resolver требует отдельного R&D | — Pending |

## Эволюция

После каждого перехода между фазами:
1. Требования аннулированы? → Переместить в «Вне скопа» с причиной
2. Требования проверены? → Переместить в «Проверенные» со ссылкой на фазу
3. Новые требования? → Добавить в «Активные»
4. Решения для журнала? → Добавить в «Ключевые решения»

После каждого milestone:
1. Полный review всех секций
2. Core Value check — всё ещё верен?
3. Audit Out of Scope — причины всё ещё актуальны?

---
*Последнее обновление: 2026-06-03 — старт milestone v1.1 Ingestion Pipeline*
