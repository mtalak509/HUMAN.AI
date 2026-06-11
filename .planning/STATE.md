---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Ingestion Pipeline
status: in_progress
last_updated: "2026-06-11T15:09:00Z"
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 9
  completed_plans: 1
  percent: 11
---

# Состояние проекта

## Ссылка на проект

См.: .planning/PROJECT.md (обновлён 2026-06-03)

**Ключевая ценность:** Загрузил PDF-резюме → кандидат появился в графе с experience, education, skills — без ручного ввода
**Текущий фокус:** Milestone v1.1 — Ingestion Pipeline

## Текущая позиция

Фаза: 4 — PDF-парсер (выполняется)
План: 04-01 ✅ ВЫПОЛНЕН → следующий: 04-02
Статус: Executing — план 04-01 завершён, 04-02 готов к старту
Последняя активность: 2026-06-11 — Выполнен план 04-01 (core/parser, Settings.storage_root, unit tests)
Resume: .planning/phases/04-pdf/04-02-PLAN.md

Прогресс: [█░░░░░░░░░] 11%

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
Остановились на: План 04-01 выполнен — core/parser готов, unit тесты зелёные
Файл возобновления: .planning/phases/04-pdf/04-02-PLAN.md
