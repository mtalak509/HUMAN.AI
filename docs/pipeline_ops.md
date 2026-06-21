# Шпаргалка: ingestion-пайплайн (Redis / worker / FastAPI)

Краткая справка по тому, как устроен прогон одного резюме в граф и как за ним наблюдать.

## Мысленная модель: три отдельных процесса

```
   ты (curl)
      │  POST /documents
      ▼
 ┌─────────┐   кладёт задачу   ┌─────────┐   забирает задачу   ┌─────────┐
 │ fastapi │ ───────────────▶  │  redis  │  ◀───────────────── │ worker  │
 │  (API)  │                   │(очередь)│                     │(обработ)│
 └─────────┘                   └─────────┘                     └────┬────┘
                                                                    │ пишет результат
                                                                    ▼
                                                               ┌─────────┐
                                                               │  neo4j  │
                                                               └─────────┘
```

Три разных контейнера = три разных процесса:

| Процесс | Что это | Роль |
|---|---|---|
| **redis** | хранилище-очередь (тупая труба) | держит список задач «обработай документ X». Сам ничего не обрабатывает и про резюме не знает. |
| **worker** | отдельный процесс (Celery) | опрашивает Redis, берёт задачу, выполняет `parse → extract → write`. Делает всю работу. |
| **fastapi** | API (uvicorn) | принимает PDF, кладёт задачу в Redis, отвечает `202`. |

Ключевое: **worker — отдельный процесс, НЕ часть Redis.** Redis — труба, worker — исполнитель.

## Поток обработки одного резюме

1. `POST /documents` → проверки (.pdf, ≤10 МБ), `document_id = SHA-256(байты)`, сохранение PDF на диск, узел `Document(status=queued)` в Neo4j, задача в Redis → ответ `202`.
2. Задача лежит в Redis, пока её не заберёт worker (передаётся только `document_id`).
3. worker: `processing` → **parse** (PDF→текст) → **extract** (LLM/OpenRouter) → **write** (граф) → `written`.
4. Любая ошибка стадии → `failed` + `failed_stage` (`parse|extract|write`) + `error`. Автоповтора нет (fail-fast).
5. Финальный статус читается из Neo4j через `GET /documents/{id}`.

## Запуск стека

```bash
# пересобрать образ и поднять всё (neo4j, qdrant, redis, fastapi, worker)
docker compose up -d --build

# проверить, что worker поднялся и подключился к Redis
docker compose logs -f worker
# ждём: "Connected to redis://redis:6379//", "celery@... ready",
#       в списке задач — process_document
```

## Прогон резюме

```bash
# отправить реальное резюме
curl -F "file=@rnd/data/resume/Talakin.pdf" http://localhost:8000/documents
# -> {"document_id":"<sha256>","task_id":"..."}

# опросить статус (queued -> processing -> written)
curl http://localhost:8000/documents/<sha256>
# -> {"processing_status":"written"}  ← кандидат в графе
```

## Наблюдение: куда смотреть

### Логи воркера (что он делает прямо сейчас)
```bash
docker compose logs -f worker
```
При прогоне видно:
```
pipeline: processing started doc_id=...
pipeline: parse OK doc_id=... chars=3421
pipeline: extract OK doc_id=...
pipeline: write OK doc_id=...
pipeline: pipeline complete doc_id=...
```

### Заглянуть в очередь Redis (что ждёт)
```bash
docker compose exec redis redis-cli
```
В консоли Redis:
```
KEYS *                  # какие ключи есть
LLEN celery             # сколько задач ждёт (celery — имя очереди по умолчанию)
LRANGE celery 0 -1      # сами задачи (JSON с document_id)
```
Обычно `LLEN celery` = `0`: задача забирается мгновенно. Очередь растёт, только если задач больше, чем worker успевает.

### Спросить у самого воркера (через Celery, не Redis)
```bash
docker compose exec worker celery -A core.pipeline.celery_app inspect active     # что выполняется сейчас
docker compose exec worker celery -A core.pipeline.celery_app inspect registered # какие задачи worker знает
docker compose exec worker celery -A core.pipeline.celery_app status             # жив ли worker
```

## Важно: «всю историю задач» посмотреть нельзя — это by design (D-03)

У нас **нет result backend** — Celery нигде не хранит результаты/историю выполненных задач.

| Состояние задачи | Где смотреть |
|---|---|
| Ждёт в очереди (ещё не взята) | Redis: `LLEN celery` / `LRANGE celery 0 -1` |
| Выполняется прямо сейчас | `celery inspect active` |
| Завершена (успех/провал) | **Нигде в Celery!** Только в Neo4j: статус на узле `Document` → `GET /documents/{id}` |

Единственный источник правды о судьбе документа — узел `Document` в Neo4j, а не очередь. Redis — расходник: задача проехала и исчезла.

## Достать кандидатов из графа

```bash
# все кандидаты (быстрый разовый запрос)
docker compose exec neo4j cypher-shell -u neo4j -p <PASSWORD> \
  "MATCH (c:Candidate) RETURN c.id, c.full_name, c.status"
```
Или через библиотеку запросов `scripts/queries.py`.

## Частые проблемы

| Симптом | Причина | Что проверить |
|---|---|---|
| Статус навсегда `queued` | worker не запущен / не подключён к Redis | `docker compose logs worker` |
| `failed`, `failed_stage: extract` | нет/неверный `OPENROUTER_API_KEY` | `.env`, который читает контейнер |
| `failed`, `failed_stage: parse`, `FileNotFoundError` | API и worker не видят общий `storage/` | оба сервиса монтируют `.:/app` |
| API-контейнер не стартует | отсутствует зависимость | пересобрать образ `--build` |
