---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: milestone
status: Phase 7 COMPLETE — all 3 plans done (07-01 ✅, 07-02 ✅, 07-03 ✅); milestone v1.1 complete
last_updated: "2026-06-14T19:05:17.744Z"
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 9
  completed_plans: 9
  percent: 100
---

# Состояние проекта

## Ссылка на проект

См.: .planning/PROJECT.md (обновлён 2026-06-03)

**Ключевая ценность:** Загрузил PDF-резюме → кандидат появился в графе с experience, education, skills — без ручного ввода
**Текущий фокус:** Milestone v1.1 — Ingestion Pipeline

## Текущая позиция

Фаза: 7 — Ingestion API ЗАВЕРШЕНА (07-01 ✅, 07-02 ✅, 07-03 ✅)
Статус: MILESTONE v1.1 COMPLETE — PDF-резюме через POST /documents → Neo4j граф → find_candidates_by_skill подтверждён end-to-end
Последняя активность: 2026-06-14 — 07-03 выполнен: tests/test_ingestion_e2e.py (2 e2e теста, все зелёные)
Resume: N/A (фаза завершена)

Прогресс: [██████████] 100%

## Накопленный контекст

### Решения

- Граф — источник правды, Qdrant — индекс (KAG-паттерн) ✓
- json_object + Pydantic + 1 retry — дефолт экстрактора (smoke-test: 0 ошибок) ✓
- PDF only для парсера v1 (DOCX и OCR — вне скопа) ✓
- Entity Resolver — не в v1.1, каждое резюме = новый кандидат ✓
- Полноценный R&D пропускаем — smoke-test достаточен ✓
- MERGE-ключи: Candidate.id, Skill.name, Company.name, Role.title (из migrations.py) ✓
- PyPdfBackend: ("", "empty") когда все страницы пустые — маркеры не включаются ✓
- storage_root: Path = Path("storage") в Settings, env STORAGE_ROOT ✓
- ParseResult.file_uri / text_uri — относительные пути (не абсолютные) ✓
- openrouter_api_key добавлен в Settings как str | None для совместимости с .env ✓
- ExtractedCandidate: поля verbatim из rnd Resume (D-04); is_current = computed_field (D-05); провенанс document_id+model_version (D-02); без переименования под онтологию (D-06) ✓
- extractor config knobs в Settings: extractor_model/openrouter_base_url/extractor_timeout/extractor_temperature с дефолтами smoke-test ✓
- Extractor.extract: async, run_in_executor offload, json_object + Pydantic + 1 retry (EXTR-01/02) ✓
- document_id + model_version штампуются в _validate() — авторитет вызова, не LLM (D-02/D-03) ✓
- 5/5 резюме без ValidationError в live integration-тесте (критерий #4) ✓
- failure-policy: 2-й retry-провал пробрасывает ValidationError (propagate, D-discretion) ✓
- Document MERGE: SET (не ON CREATE SET) — повторный парсинг обновляет тот же узел, без дублей ✓
- is_connected guard перед session() — graceful degradation при недоступном Neo4j ✓
- corpus smoke-тест работает с db=None — независим от инфры ✓
- datetime.UTC alias (Python 3.11+) вместо timezone.utc ✓
- cypher.py — единственная Cypher-библиотека GraphWriter: все запросы параметризованы ($param), plain SET (не ON CREATE SET), Document всегда MATCH (не MERGE) ✓
- USED_SKILL (D-06) — новый тип ребра Experience->Skill без constraint (рёбра не имеют uniqueness-ключей) ✓
- LINK_SUPPORTS_SKILL / LINK_SUPPORTS_EXPERIENCE — разные константы (D-03: has_skill→Skill, worked_at→Experience) ✓
- candidate_id = document_id (D-01) — sha1 helpers для experience/education/contact/fact ids ✓
- Fact.confidence = None (D-02) — grep подтверждает: нет float-литералов ✓
- Один Fact на уникальный навык (D-07) — по объединённому множеству, без дублей ✓
- GraphWriter DI-конструктор (db=None safe) + is_connected guard + graceful degradation (T-06-07) ✓
- execute_write + одна транзакция для атомарности; Document только MATCH-ится (T-06-02) ✓
- D-03: NO Celery result backend — processing_status на Neo4j Document node — единственный источник истины ✓
- D-07: fail-fast Celery task — нет autoretry_for; 1-retry экстрактора сохранён ✓
- D-06: failed_stage (parse|extract|write) + error[:2000] на Document при ошибке ✓
- T-07-03: is_connected=False → RuntimeError до старта pipeline (никогда silent success) ✓
- merge_document_queued: ON CREATE SET — re-POST in-flight doc не затирает статус (D-05) ✓
- reset_for_requeue: обнуляет error/failed_stage=null для свежести при повторной постановке (D-05/D-06) ✓
- api/dependencies.py: get_db/get_settings DI хелперы вынесены в отдельный модуль (circular import api/main ↔ api/routers) ✓
- D-04 ordering: merge_document_queued вызывается ВНУТРИ async-with-session, process_document.delay — ПОСЛЕ закрытия сессии ✓
- D-05 dedup: _read_status одним Cypher-запросом до любой записи; written→200/null, queued|processing→202/null, failed→reset+202/task_id ✓
- 413 int literal (не HTTP_413_REQUEST_ENTITY_TOO_LARGE — deprecated в FastAPI) ✓
- httpx.AsyncClient + ASGITransport вместо TestClient для e2e тестов с session-scoped async Neo4j fixtures (избегает "Future attached to different loop" на Windows ProactorEventLoop) ✓
- await _run(document_id) напрямую вместо Celery eager mode в async тестах (asyncio.run() не может быть вызван из running event loop) ✓
- _FakeExtractor plain class вместо AsyncMock — AsyncMock создаёт futures, привязанные к loop создания (cross-loop safe) ✓

### Ожидающие задачи

Нет.

### Блокеры / опасения

Нет.

## Отложенные элементы

| Категория | Элемент | Статус | Отложен в |
|-----------|---------|--------|-----------|
| Eval baseline | precision/recall на 20 резюме | v2 | v1.1 |
| DOCX/OCR парсер | Поддержка не-PDF форматов | v2 | v1.1 |
| Entity Resolver | Дедупликация кандидатов | v1.2 | v1.1 |

## Непрерывность сессий

Последняя сессия: 2026-06-14
Остановились на: 07-03 DONE — e2e тест выполнен, 2 теста зелёные, milestone v1.1 complete
Файл возобновления: N/A (фаза завершена)
