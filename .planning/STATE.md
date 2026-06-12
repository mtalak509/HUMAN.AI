---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: milestone
status: in_progress
last_updated: "2026-06-12T17:59:41.840Z"
progress:
  total_phases: 4
  completed_phases: 2
  total_plans: 4
  completed_plans: 4
  percent: 100
---

# Состояние проекта

## Ссылка на проект

См.: .planning/PROJECT.md (обновлён 2026-06-03)

**Ключевая ценность:** Загрузил PDF-резюме → кандидат появился в графе с experience, education, skills — без ручного ввода
**Текущий фокус:** Milestone v1.1 — Ingestion Pipeline

## Текущая позиция

Фаза: 6 — Graph Writer (планирование)
Статус: Фаза 6 — контекст собран (06-CONTEXT.md, решения D-01…D-08); следующий шаг: /gsd-plan-phase 6
Последняя активность: 2026-06-12 — discuss-phase 6: закрыто открытое решение ExtractedCandidate→Fact + Fact.confidence=null
Resume: .planning/phases/06-graph-writer/06-CONTEXT.md

Прогресс: [████░░░░░░] 44%

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
Остановились на: discuss-phase 6 завершён — 06-CONTEXT.md (D-01…D-08); готово к /gsd-plan-phase 6
Файл возобновления: .planning/phases/06-graph-writer/06-CONTEXT.md
