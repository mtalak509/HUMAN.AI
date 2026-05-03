# Roadmap: HUMAN.AI — Фаза 0

## Обзор

Фаза 0 — инфраструктурный фундамент Talent Intelligence Platform. Цель: поднять локальный стек одной командой, закодировать онтологию графа, загрузить тестовых кандидатов и убедиться, что базовые Cypher-запросы работают. Без этого фундамента все последующие фазы (парсер, LLM-экстрактор, retrieval) не имеют куда писать.

**Критерий выхода из Фазы 0:** `docker compose up -d` поднимает весь стек, в Neo4j лежат 15 тестовых кандидатов, `pytest tests/test_infra.py` проходит зелёным.

## Фазы

- [ ] **Фаза 1: Инфраструктурный скелет** - FastAPI-приложение запускается, читает конфиг из .env, логирует JSON, поднимается в Docker Compose вместе с Neo4j/Qdrant/Redis
- [ ] **Фаза 2: Онтология графа** - Все 12 типов узлов описаны как Pydantic-модели, constraints и indexes применены к Neo4j, async Neo4j driver готов
- [ ] **Фаза 3: Тестовые данные и eval** - 15 тестовых кандидатов в Neo4j, базовые Cypher-запросы работают, smoke-тесты проходят

## Детали фаз

### Phase 1: Инфраструктурный скелет
**Goal**: Разработчик может запустить приложение локально (`uvicorn` или `docker compose`), получить ответ от /health и быть уверен, что конфиг и логирование работают корректно
**Depends on**: Ничего (первая фаза)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, ONTO-03
**Success Criteria** (что должно быть ИСТИНОЙ):
  1. `GET /health` возвращает `200 OK` с телом `{"status": "ok"}` при запуске через `uvicorn api.main:app --reload`
  2. Изменение `.env` меняет поведение приложения без правки кода (Neo4j URI, log_level и т.д.)
  3. Логи приложения выводятся через loguru: цветной human-readable формат в консоли, уровень управляется через Settings.log_level
  4. `docker compose up -d` поднимает Neo4j, Qdrant, Redis и FastAPI; FastAPI-контейнер проходит health-check
  5. `core/graph.py` подключается к Neo4j, метод `ping()` возвращает успех, context-manager сессий работает без утечек

**Plans**: 3 плана

Plans:
- [ ] 01-01: FastAPI-скелет — `api/main.py`, роут `/health`, точка входа приложения
- [ ] 01-02: Конфигурация и логирование — `core/config.py` (pydantic-settings), loguru с цветным выводом в консоль
- [ ] 01-03: Docker Compose — добавить FastAPI-сервис, health-check, `core/graph.py` с async Neo4j driver

### Phase 2: Онтология графа
**Goal**: Онтология графа закодирована как Pydantic-модели и применена к Neo4j через идемпотентные миграции — любой следующий компонент может писать в граф по известной схеме
**Depends on**: Фаза 1
**Requirements**: ONTO-01, ONTO-02
**Success Criteria** (что должно быть ИСТИНОЙ):
  1. `core/models.py` содержит все 12 типов узлов (Candidate, Contact, Skill, Role, Company, Experience, Education, Vacancy, Status, HRNote, Document, Fact) с полями из раздела 4.2 `core_architecture.md`
  2. `python scripts/migrate.py` применяет constraints и indexes к Neo4j; повторный запуск не ломает ничего и завершается без ошибок
  3. После миграции Neo4j browser показывает уникальные constraint'ы на ключевых полях (например, `Candidate.id`) и indexes для быстрого поиска

**Plans**: 2 плана

Plans:
- [ ] 02-01: Pydantic-модели онтологии — `core/models.py`, все 12 типов узлов с аннотациями типов
- [ ] 02-02: Скрипт миграции — `scripts/migrate.py`, Cypher constraints и indexes, идемпотентность

### Phase 3: Тестовые данные и eval
**Goal**: В Neo4j лежат реалистичные тестовые кандидаты, базовые Cypher-запросы возвращают ожидаемые результаты, smoke-тесты инфраструктуры проходят — фундамент проверен без LLM
**Depends on**: Фаза 2
**Requirements**: SEED-01, SEED-02, TEST-01, TEST-02
**Success Criteria** (что должно быть ИСТИНОЙ):
  1. `python scripts/seed.py` загружает 15 кандидатов с полным набором связей (Skills, Experience → Company/Role, Education, HRNote, Document, Fact); повторный запуск не создаёт дублей
  2. Запросы из `scripts/queries.py` (поиск по навыку, по опыту в компании, по статусу) возвращают корректные кандидаты из seed-набора
  3. `pytest tests/test_infra.py` проходит зелёным: Neo4j `RETURN 1`, Qdrant `/health`, Redis `ping` — все три успешны
  4. pytest-фикстуры `settings`, `neo4j_driver`, `qdrant_client` из `tests/conftest.py` доступны любому тесту без повторной инициализации

**Plans**: 3 плана

Plans:
- [ ] 03-01: Seed-скрипт — `scripts/seed.py`, 15 кандидатов с полным графом связей через MERGE
- [ ] 03-02: Примеры Cypher-запросов — `scripts/queries.py`, документированные запросы поиска
- [ ] 03-03: Eval-харнес — `tests/conftest.py` с фикстурами, `tests/test_infra.py` со smoke-тестами

## Прогресс

| Фаза | Планов выполнено | Статус | Завершена |
|------|-----------------|--------|-----------|
| 1. Инфраструктурный скелет | 0/3 | Не начата | - |
| 2. Онтология графа | 0/2 | Не начата | - |
| 3. Тестовые данные и eval | 0/3 | Не начата | - |
