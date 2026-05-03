# Phase 1: Инфраструктурный скелет - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the discussion history.

**Date:** 2026-05-03
**Phase:** 01-infrastructure-skeleton
**Mode:** discuss (default)
**Areas discussed:** FastAPI startup pattern, Инициализация приложения, Логирование

---

## Gray Areas Presented

| Area | Description |
|------|-------------|
| FastAPI startup pattern | lifespan vs. startup event vs. module singleton |
| FastAPI in Docker | Dockerfile vs. Python image vs. local-only |
| Health check depth | Simple ping vs. connectivity checks |
| Log format | Console format with loguru |

**User selected:** FastAPI startup pattern (остальные — Claude's discretion или раскрыты в ходе обсуждения)

---

## Discussion Log

### FastAPI startup pattern

**Q:** Как инициализировать async Neo4j driver?
**A:** Пользователь хотел обсудить полную структуру инициализации — lifespan, все составляющие.

**Q:** Через app.state или Depends?
**Options:** Depends + get_db() / request.app.state.db напрямую
**A:** Depends + get_db() — стандартный FastAPI паттерн, легко переопределить в тестах.

**Q:** Как Settings передаётся в GraphDB и роуты?
**Options:** get_settings() Depends + lifespan / @lru_cache singleton
**A:** get_settings() Depends + lifespan — один инстанс, тесты переопределяют через dependency_overrides.

**Q:** Что делает приложение если Neo4j недоступен при старте?
**Options:** Fail fast / Lazy connect
**A (freeform):** Фоновый retry, 3 попытки с увеличенными таймаутами. При неудаче — graceful degradation. Основной сервис продолжает работать.

**Q:** Если Neo4j недоступен после 3 ретраев, что возвращает /health?
**Options:** 200 + degraded status / 503
**A:** 200 + {"status": "degraded", "neo4j": "unavailable"} — Docker health-check проходит.

### Логирование

**Q (freeform, по инициативе пользователя):** Обсудить настройку loguru — как определён config-файл, как инициализирован loguru, доступные уровни.

**Q:** Формат консольных логов?
**Options:** Standard с временем / Verbose с модулем / Minimal
**A:** Verbose с модулем: `{time:HH:mm:ss} | {level:<8} | {name}:{line} | {message}`

**Q:** Уровни логирования?
**Options:** DEBUG/INFO/WARNING/ERROR / TRACE+
**A:** TRACE / DEBUG / INFO / WARNING / ERROR

**Q:** JSON-режим нужен?
**Options:** Нет / JSON по флагу LOG_JSON=true
**A:** JSON по флагу LOG_JSON=true → serialize=True в loguru.add()

**Q (freeform, уточнение):** Паттерн — core/logger.py один раз переопределяет стандартный логгер, потом везде `from loguru import logger`?
**A:** Подтверждено — именно так. setup_logging() вызывается в lifespan, везде просто `from loguru import logger`.

---

## Claude's Discretion

- Docker Compose для FastAPI (Dockerfile vs. Python image) — не обсуждалось, Claude выбирает
- Точный механизм retry (tenacity vs. asyncio.sleep вручную)
- Конкретные таймауты retry
- Структура `.env.example`

---

## Deferred Ideas

- Correlation ID (OBS-01) — v2 требование
- Метрики latency (OBS-02) — v2 требование
