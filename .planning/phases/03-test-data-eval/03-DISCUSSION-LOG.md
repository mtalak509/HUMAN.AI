# Phase 3: Тестовые данные и eval - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in 03-CONTEXT.md — this log preserves the discussion.

**Date:** 2026-05-07
**Phase:** 03-test-data-eval
**Mode:** default (interactive)
**Areas discussed:** Профиль seed-кандидата, Формат queries.py, seed.py и core/schemas/models.py

---

## Профиль seed-кандидата

| Вопрос | Варианты | Выбор |
|--------|----------|-------|
| Насколько полный граф? | Максимальный (все 12 узлов) / Минимальный | Максимальный |
| Домен кандидата? | Senior Python/ML / HR-менеджер / Вы решаете | Senior Python/ML |
| Fact + Document связаны? | Да, полный provenance / Fact без Document | Да, Fact + Document |

**Ратionale:** Один кандидат с полным графом проверяет всю онтологию Phase 2 за один прогон.

---

## Формат queries.py

| Вопрос | Варианты | Выбор |
|--------|----------|-------|
| Формат файла? | Исполняемый скрипт / Библиотека функций / Строки Cypher | Библиотека функций |
| Какие функции? | 3 из ROADMAP / 3 + бонус get_full_graph | 3 функции из ROADMAP |

**Rationale:** Библиотека функций повторно используется в тестах. Три функции точно закрывают SEED-02.

---

## seed.py и core/schemas/models.py

| Вопрос | Варианты | Выбор |
|--------|----------|-------|
| Как создаются узлы? | Pydantic-модели → MERGE / Raw Cypher | Pydantic-модели → MERGE |
| MERGE-ключи? | Candidate.id + Skill.name + Company.name + Role.title / Только Candidate.id | Все 4 ключа |

**Rationale:** Использование Pydantic-моделей консистентно со схемой Phase 2. MERGE-ключи идентичны будущему LLM-экстрактору.

---

## Deferred Ideas

- Несколько кандидатов для edge cases — при необходимости позже
- `scripts/reset.py` — UTIL-01, вне Phase 3
