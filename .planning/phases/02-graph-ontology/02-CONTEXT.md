# Phase 2: Онтология графа - Context

**Gathered:** 2026-05-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Закодировать онтологию графа как Pydantic-модели в `core/models.py` и применить Cypher constraints/indexes через идемпотентный `scripts/migrate.py`. Любой следующий компонент (Graph Writer, LLM-экстрактор) может писать в граф по известной схеме.

Scope: `core/models.py` (12 типов узлов), `scripts/migrate.py` (constraints + indexes).

Вне скопа: seed-данные, Graph Writer, LLM-извлечение, Qdrant-коллекции.

</domain>

<decisions>
## Implementation Decisions

### Структура Pydantic-моделей
- **D-01:** Каждый из 12 узлов — отдельный `BaseModel` без общего базового класса. Нет `GraphNode`-иерархии. Поля `id` и `created_at` повторяются в каждой модели явно.

### Опциональность полей
- **D-02:** Required только идентификационные поля — минимум, без которого узел не имеет смысла (например, `id: str`, `name: str` для Skill, `full_name: str` для Candidate). Всё остальное — `Optional[...] = None`. Это допускает частичные данные из LLM-извлечения и неполные резюме.

### Скрипт миграции
- **D-03:** `scripts/migrate.py` — standalone скрипт. Запускается явно: `python scripts/migrate.py`. Читает Settings из `.env` через `get_settings()`, создаёт `GraphDB`, применяет `CREATE CONSTRAINT IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`, закрывает соединение. Не вызывается из lifespan приложения.
- **D-04:** Идемпотентность через Neo4j 5.x синтаксис `IF NOT EXISTS` — повторный запуск безопасен и не ломает существующую схему.

### Claude's Discretion
- Enum-стратегия для статусов (`Status.name`: rejected/in_progress/offered/hired/withdrawn), типов документов, типов контактов — Python `Literal[...]` или `str` по усмотрению реализации.
- Точный набор constraints (уникальные поля) и indexes (поля поиска) по каждому типу — определяется из `core_architecture.md` §4.2–4.3.
- Структура `asyncio.run(main())` в migrate.py.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Онтология и схема
- `core_architecture.md` §4.2 — Все 12 типов узлов с ключевыми свойствами (MUST READ — это источник правды для полей моделей)
- `core_architecture.md` §4.3 — Ключевые связи между узлами
- `core_architecture.md` §4.4 — Логика провенанса через Fact-узел

### Требования фазы
- `.planning/REQUIREMENTS.md` §Онтология — ONTO-01, ONTO-02 (критерии приёмки)
- `.planning/ROADMAP.md` §Phase 2 — Success Criteria (3 проверяемых утверждения)

### Существующий код (интеграция)
- `core/graph.py` — AsyncDriver wrapper, `session()` context manager — migrate.py использует его для подключения
- `core/config.py` — `get_settings()` с `@lru_cache` — migrate.py импортирует напрямую
- `pyproject.toml` — версии зависимостей (neo4j>=5.20, pydantic>=2.0)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `core/graph.py` → `GraphDB.session()` async context manager — migrate.py создаёт экземпляр и вызывает `connect_with_retry()` + `session()` для выполнения Cypher
- `core/config.py` → `get_settings()` — прямой импорт для чтения Neo4j URI/credentials из `.env`

### Established Patterns
- Pydantic v2 уже используется в `core/config.py` (`BaseSettings`) — модели в `core/models.py` следуют тому же стилю: `Field(default=...)`, аннотации типов Python 3.10+ (`str | None`)
- Async everywhere: `core/graph.py` — полностью async. `scripts/migrate.py` должен использовать `asyncio.run(main())`

### Integration Points
- `core/models.py` → потребляется Graph Writer (Фаза 1 продакшн) и LLM-экстрактором (будущие фазы) для создания/валидации узлов перед записью
- `scripts/migrate.py` → запускается вручную или в CI перед первым стартом приложения; не интегрирован в lifespan

</code_context>

<specifics>
## Specific Ideas

- Критерий приёмки ONTO-02 явно называет `python scripts/migrate.py` — standalone запуск зафиксирован в ROADMAP, не менять.
- После миграции Neo4j Browser должен показывать constraints на `Candidate.id`, `Skill.name` и т.д. — это проверяемый артефакт из Success Criteria фазы.

</specifics>

<deferred>
## Deferred Ideas

- Graph Writer (универсальный `node_to_cypher(node)`) — Фаза 1 продакшн / отдельная фаза
- `scripts/reset.py` (очистка Neo4j) — v2 требование UTIL-01, не Phase 2
- `scripts/check_ontology.py` (проверка constraints) — v2 требование UTIL-02

</deferred>

---

*Phase: 02-graph-ontology*
*Context gathered: 2026-05-04*
