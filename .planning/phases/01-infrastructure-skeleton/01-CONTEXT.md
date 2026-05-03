# Phase 1: Инфраструктурный скелет - Context

**Gathered:** 2026-05-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Разработчик может запустить приложение локально (`uvicorn` или `docker compose`), получить ответ от `/health` и быть уверен, что конфиг и логирование работают корректно.

Scope: `api/main.py`, `core/config.py`, `core/logger.py`, `core/graph.py`, Dockerfile, docker-compose.yml (FastAPI сервис).

Вне скопа этой фазы: парсер, LLM-экстрактор, Pydantic-модели онтологии, seed-данные, Qdrant/Celery.

</domain>

<decisions>
## Implementation Decisions

### FastAPI startup pattern
- **D-01:** Использовать `lifespan` asynccontextmanager (`@asynccontextmanager async def lifespan(app)`) — передаётся в `FastAPI(lifespan=lifespan)`. Никаких `@app.on_event`.
- **D-02:** `Settings` инициализируется в lifespan, хранится в `app.state.settings`. `GraphDB` инициализируется в lifespan, хранится в `app.state.db`.
- **D-03:** Роуты получают зависимости через `Depends(get_settings)` и `Depends(get_db)` — функции читают из `request.app.state`. Тесты переопределяют через `dependency_overrides`.

### Neo4j connection resilience
- **D-04:** При старте вызывается `ping()`. Если Neo4j недоступен — 3 ретрая с увеличивающимися таймаутами (например, 1s → 3s → 9s). После 3 неудач — graceful degradation: приложение продолжает работать, статус Neo4j = "unavailable".
- **D-05:** `GraphDB` в `core/graph.py` предоставляет: async driver, `ping()`, context manager для сессий (`async with db.session() as s`), `close()`.

### Health check
- **D-06:** `GET /health` всегда возвращает `200 OK`. Тело: `{"status": "ok"}` если Neo4j доступен, `{"status": "degraded", "neo4j": "unavailable"}` если нет. Docker health-check не падает в degraded.

### Конфигурация (Settings)
- **D-07:** `core/config.py` — `Settings(BaseSettings)` читает `.env`. Поля как минимум: `neo4j_uri`, `neo4j_user`, `neo4j_password`, `qdrant_url`, `redis_url`, `log_level`, `log_json`.
- **D-08:** `get_settings()` — функция, возвращает `Settings()`. Может быть закэширована через `@lru_cache` для переиспользования в Depends.

### Логирование (loguru)
- **D-09:** `core/logger.py` содержит `setup_logging(level: str, json_mode: bool)`. Вызывается один раз в lifespan после инициализации Settings.
- **D-10:** Паттерн: `logger.remove()` → `logger.add(sys.stderr, level=level, format=..., colorize=True)` (или `serialize=True` для JSON).
- **D-11:** Консольный формат (verbose): `{time:HH:mm:ss} | {level:<8} | {name}:{line} | {message}` с colorize=True.
- **D-12:** Доступные уровни: TRACE / DEBUG / INFO / WARNING / ERROR — управляются через `Settings.log_level` (env var `LOG_LEVEL`).
- **D-13:** JSON-режим: `LOG_JSON=true` в `.env` → `Settings.log_json = True` → `serialize=True` в `logger.add()`.
- **D-14:** Везде в приложении: `from loguru import logger` — loguru global singleton, настроен один раз в `setup_logging()`.

### Claude's Discretion
- Docker Compose: Dockerfile + build vs. Python image+command — Claude выбирает (рекомендую Dockerfile с volume mount для hot-reload).
- Точная реализация retry логики (asyncio.sleep, tenacity, или вручную).
- `.env.example` структура.
- Конкретные таймауты retry (рекомендую 1s/3s/9s).

</decisions>

<specifics>
## Specific Ideas

- Retry при старте: 3 попытки с экспоненциальным ростом таймаута. После неудачи — graceful degradation, не краш.
- `/health` всегда 200 — чтобы Docker health-check не убивал контейнер когда Neo4j ещё не поднялся.
- core/logger.py — единственное место настройки loguru. Остальные модули только импортируют `from loguru import logger`.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Архитектура и стек
- `core_architecture.md` — Полная архитектурная референция: онтология графа, компоненты, потоки данных. Читать перед любыми структурными решениями.
- `CLAUDE.md` — Инструкции для Claude: стек, команды, ключевые архитектурные правила.

### Требования
- `.planning/REQUIREMENTS.md` §Инфраструктура — INFRA-01..04, ONTO-03 (критерии приёмки для Phase 1)
- `.planning/ROADMAP.md` §Phase 1 — Success Criteria (5 проверяемых утверждений)

### Зависимости и конфиг
- `pyproject.toml` — версии всех зависимостей (fastapi>=0.115, neo4j>=5.20, loguru>=0.7, pydantic-settings>=2.3)
- `docker-compose.yml` — текущая конфигурация инфра-сервисов (Neo4j, Qdrant, Redis); Phase 1 добавляет FastAPI-сервис

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Нет Python-кода — `api/` и `core/` содержат только `.gitkeep`. Всё создаётся с нуля.

### Established Patterns
- `docker-compose.yml` уже настроен для Neo4j (port 7687), Qdrant (6333), Redis (6379) — Phase 1 добавляет FastAPI без изменения существующих сервисов.
- `pyproject.toml` — все зависимости уже объявлены, включая `loguru>=0.7`, `neo4j>=5.20`, `pydantic-settings>=2.3`.
- Naming: Python файлы `snake_case.py`, Pydantic модели `PascalCase`, pytest с `asyncio_mode = "auto"`.

### Integration Points
- `core/graph.py` → `docker-compose.yml`: Neo4j URI = `neo4j://neo4j:7687` (внутри Docker сети), `bolt://localhost:7687` (локально).
- `core/config.py` → `.env` (не в git): читает через pydantic-settings BaseSettings.
- `api/main.py` → `core/graph.py`, `core/logger.py`, `core/config.py`: всё через lifespan и Depends.

</code_context>

<deferred>
## Deferred Ideas

- Correlation ID через pipeline (request → Celery → writer) — v2 требование OBS-01, не Phase 1.
- Метрики latency для шагов ingestion — OBS-02, не Phase 1.
- JSON логи для ELK/prod — архитектура заложена (LOG_JSON флаг), настройка среды — Phase 4+.

</deferred>

---

*Phase: 01-infrastructure-skeleton*
*Context gathered: 2026-05-03*
