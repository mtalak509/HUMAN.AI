# Phase 2: Онтология графа - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the discussion.

**Date:** 2026-05-04
**Phase:** 02-graph-ontology
**Mode:** discuss (default)
**Areas discussed:** Структура моделей, Опциональность полей, Дизайн migrate.py

---

## Areas Discussed

### Структура Pydantic-моделей

| Option | Description |
|--------|-------------|
| GraphNode базовый класс | id + created_at вынесены в GraphNode(BaseModel), все 12 узлов наследуют |
| Плоские BaseModel | Каждый из 12 узлов — отдельный BaseModel без общего предка |

**User selected:** Плоские BaseModel

**Notes:** Пользователь уточнил разницу — GraphNode удобнее для Graph Writer (`isinstance` + универсальный serialize), но для текущей фазы плоские модели проще и прямолинейнее. Дублирование `id`/`created_at` допустимо на 12 моделях.

---

### Опциональность полей

| Option | Description |
|--------|-------------|
| Минимальные required | Required только идентификационные поля, остальное Optional |
| Строгая схема | Больше required-полей, валидация падает на неполных данных |

**User selected:** Минимальные required

**Notes:** Реальные резюме неполные, LLM-извлечение пропускает поля — строгая схема создаст проблемы уже в Фазе 3 (seed) и Фазе 1 продакшн (экстрактор).

---

### Дизайн migrate.py

| Option | Description |
|--------|-------------|
| Standalone скрипт | `python scripts/migrate.py` — явный запуск отдельно от приложения |
| Через lifespan FastAPI | Автоматически при старте, удобнее в Docker |

**User selected:** Standalone скрипт

**Notes:** Пользователь уточнил разницу. Standalone выбран т.к.: (1) ROADMAP.md явно называет `python scripts/migrate.py` в Success Criteria ONTO-02; (2) тесты не запускают миграцию случайно; (3) явный контроль над когда и как применяется схема.

---

## Areas Not Discussed (Claude's Discretion)

- **Enum-стратегия** (Area 3 — не выбрана пользователем): типы для Status.name, Document.type, Contact.type — на усмотрение реализации.

## Deferred Ideas

- Graph Writer (`node_to_cypher`) — будущая фаза
- `scripts/reset.py`, `scripts/check_ontology.py` — v2 требования

---

*Discussion: 2026-05-04*
