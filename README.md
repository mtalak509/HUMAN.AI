# HUMAN.AI

Talent Intelligence Platform backend.

Сервис принимает резюме и заметки рекрутера, хранит факты и связи в Neo4j,
использует Qdrant как векторный индекс и отдает ранжированные результаты через API.

## Tech Stack

- Python 3.11+
- FastAPI
- Neo4j 5.x
- Qdrant
- Redis
- Loguru
- Docker Compose

## Project Structure

- `api/` - FastAPI приложение и роуты
- `core/` - конфигурация, логирование, доступ к графовой БД
- `tests/` - тесты (добавляются в следующих фазах)
- `.planning/` - артефакты планирования и отчеты по фазам

## Environment Configuration

Пример конфигурации находится в `.env.example`.

1. Скопируйте пример:

```bash
cp .env.example .env
```

2. Обновите минимум:

- `NEO4J_PASSWORD` - пароль Neo4j

Остальные значения по умолчанию:

- `NEO4J_URI=bolt://localhost:7687`
- `QDRANT_URL=http://localhost:6333`
- `REDIS_URL=redis://localhost:6379`
- `LOG_LEVEL=INFO`
- `LOG_JSON=false`

## Run Locally (without Docker app container)

1. Установите зависимости:

```bash
pip install -e ".[dev]"
```

2. Поднимите инфраструктуру:

```bash
docker compose up -d neo4j qdrant redis
```

3. Запустите API:

```bash
uvicorn api.main:app --reload
```

4. Проверьте health endpoint:

```bash
curl http://localhost:8000/health
```

Ожидаемый ответ:

- `{"status":"ok"}` - Neo4j доступен
- `{"status":"degraded","neo4j":"unavailable"}` - API работает, но Neo4j недоступен

## Run Full Stack with Docker Compose

```bash
docker compose up -d --build
```

Это поднимет:

- `neo4j` (7474/7687)
- `qdrant` (6333)
- `redis` (6379)
- `fastapi` (8000)

Проверка:

```bash
docker compose ps
curl http://localhost:8000/health
```

## Logging

- Конфигурируется в `core/logger.py` через `setup_logging(level, json_mode)`
- Обычный режим: цветной формат в stderr
- JSON-режим: включается через `LOG_JSON=true`

## Notes

- `.env` игнорируется git и не должен коммититься.
- `.env.example` хранится в репозитории как шаблон.
