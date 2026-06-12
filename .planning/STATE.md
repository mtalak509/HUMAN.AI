---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: milestone
status: Executing Phase 6
last_updated: "2026-06-12T18:29:19Z"
progress:
  total_phases: 4
  completed_phases: 2
  total_plans: 6
  completed_plans: 5
  percent: 83
---

# Состояние проекта

## Ссылка на проект

См.: .planning/PROJECT.md (обновлён 2026-06-03)

**Ключевая ценность:** Загрузил PDF-резюме → кандидат появился в графе с experience, education, skills — без ручного ввода
**Текущий фокус:** Milestone v1.1 — Ingestion Pipeline

## Текущая позиция

Фаза: 6 — Graph Writer (план 01 завершён)
Статус: 06-01 выполнен — core/writer/cypher.py (19 Cypher-констант) + core/writer/__init__.py; следующий шаг: план 06-02 (GraphWriter service)
Последняя активность: 2026-06-12 — 06-01: Cypher statement library завершена (WRITE-01/02/03)
Resume: .planning/phases/06-graph-writer/06-01-SUMMARY.md

Прогресс: [████████░░] 83%

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

Последняя сессия: 2026-06-12
Остановились на: 06-01 выполнен — Cypher statement library (core/writer/cypher.py + __init__.py)
Файл возобновления: .planning/phases/06-graph-writer/06-01-SUMMARY.md
