# Phase 3: Тестовые данные и eval - Context

**Gathered:** 2026-05-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Загрузить одного реалистичного тестового кандидата в Neo4j через идемпотентный seed-скрипт, реализовать три базовых Cypher-запроса как библиотеку функций, настроить pytest-фикстуры и smoke-тесты инфраструктуры — фундамент проверен без LLM.

Scope: `scripts/seed.py`, `scripts/queries.py`, `tests/conftest.py`, `tests/test_infra.py`.

Вне скопа: парсер PDF, LLM-экстрактор, Qdrant-коллекции, retrieval, векторный поиск.

</domain>

<decisions>
## Implementation Decisions

### Профиль seed-кандидата
- **D-01:** Максимально полный граф — все 12 типов узлов задействованы в одном кандидате: Candidate → Skills (3–5) + Experience→Company/Role (2 места работы) + Education + HRNote + Document + Fact. Это проверяет полноту онтологии Phase 2 и делает Cypher-запросы осмысленными.
- **D-02:** Домен кандидата — Senior Python/ML инженер. Skills: Python, FastAPI, Neo4j, machine learning (плюс 1–2 по усмотрению). Experience: 2 tech-компании с конкретными Role-узлами. Релевантно для самого проекта — легко проверить корректность.
- **D-03:** Fact-узлы связаны с Document-узлами (полный provenance-паттерн из core_architecture.md §4.4). Fact → Document → Candidate. Именно так будет работать LLM-экстрактор в Phase 1 — проверяем паттерн заранее.

### scripts/queries.py — формат
- **D-04:** `scripts/queries.py` — библиотека Python-функций, не исполняемый скрипт. Функции импортируются в тесты. Не требует `if __name__ == "__main__"` блока (хотя можно добавить для демонстрации).
- **D-05:** Три функции, точно соответствующие SEED-02:
  - `find_candidates_by_skill(driver, skill_name: str) -> list[dict]`
  - `find_candidates_by_company(driver, company_name: str) -> list[dict]`
  - `find_candidates_by_status(driver, vacancy_id: str, status: str) -> list[dict]`
  - Каждая функция принимает `AsyncDriver` и параметры, возвращает список словарей. Документирована Cypher-запросом в docstring.

### scripts/seed.py — интеграция с core/schemas/models.py
- **D-06:** `seed.py` использует Pydantic-модели из `core/schemas/models.py` для формирования данных. Поля заполняются вручную → `.model_dump()` → параметры MERGE-запросов. Консистентно со схемой Phase 2, валидирует данные перед записью.
- **D-07:** MERGE-ключи идемпотентности: `Candidate.id` (uuid4), `Skill.name`, `Company.name`, `Role.title`. Одинаково с тем, как будет работать LLM-экстрактор — паттерн проверяется заранее. Повторный запуск `python scripts/seed.py` не создаёт дублей.

### Claude's Discretion
- Конкретные имена компаний, тайтлы ролей, текст HRNote, содержимое Document/Fact — на усмотрение реализации (реалистичные, но вымышленные данные).
- Структура `asyncio.run(main())` в seed.py — аналогично migrate.py.
- Конкретный Cypher для каждой функции в queries.py — по усмотрению (соответствует схеме Phase 2).
- Scope/lifecycle фикстур conftest.py (session vs function) — на усмотрение.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Онтология и схема
- `core_architecture.md` §4.2 — Все 12 типов узлов с ключевыми свойствами (поля для Pydantic-моделей и Cypher)
- `core_architecture.md` §4.3 — Связи между узлами (что на что ссылается в MERGE)
- `core_architecture.md` §4.4 — Provenance-паттерн через Fact-узел (Fact → Document → Candidate)

### Требования фазы
- `.planning/REQUIREMENTS.md` §Тестовые данные — SEED-01, SEED-02
- `.planning/REQUIREMENTS.md` §Eval-харнес — TEST-01, TEST-02
- `.planning/ROADMAP.md` §Phase 3 — Success Criteria (4 проверяемых утверждения)

### Существующий код (интеграция)
- `core/schemas/models.py` — Pydantic-модели всех 12 типов узлов (source of truth для полей seed-данных)
- `core/database/graph.py` — GraphDB, `session()` context manager — seed.py и queries.py используют его для подключения
- `core/config.py` — `get_settings()` — прямой импорт для чтения Neo4j credentials
- `scripts/migrate.py` — структурный образец для seed.py (asyncio.run, GraphDB, get_settings)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `core/schemas/models.py` → все 12 Pydantic-моделей — seed.py создаёт экземпляры и вызывает `.model_dump()` для параметров MERGE
- `core/database/graph.py` → `GraphDB.session()` async context manager — seed.py и queries.py используют аналогично migrate.py
- `core/config.py` → `get_settings()` — прямой импорт (не через FastAPI Depends)
- `scripts/migrate.py` → паттерн `async def main() / asyncio.run(main())` — seed.py следует тому же паттерну

### Established Patterns
- MERGE-идемпотентность через `CREATE CONSTRAINT IF NOT EXISTS` уже применена в migrate.py — seed.py MERGE по тем же ключам (Candidate.id, Skill.name, Company.name, Role.title)
- Async everywhere: seed.py и queries.py используют async Neo4j driver
- Pydantic v2: `.model_dump()` для сериализации (не `.dict()`)

### Integration Points
- `tests/conftest.py` → `neo4j_driver` фикстура создаёт `GraphDB` и передаёт driver в тесты и в queries.py-функции
- `scripts/queries.py` → импортируется в тесты для проверки корректности seed-данных
- `scripts/seed.py` → запускается вручную перед тестами (`python scripts/seed.py`) или в CI

</code_context>

<specifics>
## Specific Ideas

- queries.py-функции принимают `AsyncDriver` как первый аргумент — фикстура conftest.py передаёт driver напрямую, без обёртки в GraphDB.
- Cypher-запрос документируется в docstring каждой функции — агент видит, что именно выполняется.
- Seed-кандидат должен иметь Status-узел (например, статус "in_progress" для какой-то вакансии) — иначе `find_candidates_by_status` не имеет что вернуть.

</specifics>

<deferred>
## Deferred Ideas

- Несколько кандидатов для тестирования edge cases — Phase 3 v2 или при необходимости
- `scripts/reset.py` (очистка Neo4j перед seed) — UTIL-01, не Phase 3
- Векторный поиск через Qdrant — Phase 2 продакшн

</deferred>

---

*Phase: 03-test-data-eval*
*Context gathered: 2026-05-07*
