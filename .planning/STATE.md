---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Ingestion Pipeline
status: in_progress
last_updated: "2026-06-11T17:05:00Z"
progress:
  total_phases: 4
  completed_phases: 1
  total_plans: 9
  completed_plans: 3
  percent: 33
---

# Состояние проекта

## Ссылка на проект

См.: .planning/PROJECT.md (обновлён 2026-06-03)

**Ключевая ценность:** Загрузил PDF-резюме → кандидат появился в графе с experience, education, skills — без ручного ввода
**Текущий фокус:** Milestone v1.1 — Ingestion Pipeline

## Текущая позиция

Фаза: 5 — LLM-экстрактор (в процессе, план 05-01 выполнен)
Статус: In Progress — план 05-01 завершён; 05-02 (Extractor async + retry) следующий
Последняя активность: 2026-06-11 — Выполнен план 05-01: ExtractedCandidate schema + extractor config knobs
Resume: .planning/phases/05-llm/05-02-PLAN.md

Прогресс: [███░░░░░░░] 33%

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

Последняя сессия: 2026-06-11
Остановились на: Выполнен 05-01 — ExtractedCandidate Pydantic v2 schema + is_current + config knobs; 24 теста зелёных
Файл возобновления: .planning/phases/05-llm/05-02-PLAN.md
