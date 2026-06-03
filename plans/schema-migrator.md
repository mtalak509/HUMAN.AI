# План: вынести миграции схемы в `MigrationManager`

## Цель

Один источник истины для схемы Neo4j, автоприменение на старте FastAPI, ручной запуск через `scripts/migrate.py` сохраняется как тонкая обёртка.

---

## Шаг 1. Создать `core/database/migrations.py`

Содержит:
- Константы `CONSTRAINTS: list[tuple[str, str]]` и `INDEXES: list[tuple[str, str]]` — переехали из `scripts/migrate.py` без изменений.
- Класс `SchemaMigrator` (или `MigrationManager` — на твой вкус):
  - `__init__(self, db: GraphDB)`
  - `async def apply_all(self) -> None` — гонит constraints + indexes через `db.session()`. На входе проверяет `db.is_connected`; если `False` — `logger.warning` и `return` (не raise).
  - Логирует итог: `Schema up to date: N constraints, M indexes`.

**Без** schema_version, без lock'ов, без rollback — YAGNI.

---

## Шаг 2. Переписать `scripts/migrate.py` в обёртку

Файл сжимается до ~20 строк:
- Создаёт `GraphDB`, `connect_with_retry`.
- Если `not db.is_connected` — `sys.exit(1)` (CLI-режим строже lifespan: явно падаем).
- Вызывает `SchemaMigrator(db).apply_all()`.
- В `finally` — `db.close()`.

Поведение наружу не меняется: `python scripts/migrate.py` работает как раньше.

---

## Шаг 3. Подключить в `api/main.py` lifespan

В `lifespan` после `connect_with_retry` добавить:
```python
if db.is_connected:
    from core.database.migrations import SchemaMigrator
    await SchemaMigrator(db).apply_all()
```
Если Neo4j недоступен — лог-предупреждение из `apply_all` сам сработает, приложение остаётся в degraded-режиме (контракт graceful degradation сохранён).

Импорт лучше держать на верхнем уровне, локальный импорт нужен только если хочется избежать загрузки при `is_connected=False` — но это микрооптимизация, не стоит того.

---

## Шаг 4. Тесты

В `tests/test_infra.py` (или новый `tests/test_migrations.py`):
- **Идемпотентность**: вызвать `apply_all()` дважды подряд — без ошибок, итоговый список constraints не растёт. Проверка через `SHOW CONSTRAINTS`.
- **Degraded-режим**: создать `GraphDB` без `connect_with_retry` (или с заведомо битым URI), вызвать `apply_all()` — не падает, логирует warning.
- **Smoke**: после `apply_all` в Neo4j присутствует хотя бы `candidate_id_unique`.

Тесты помечены теми же маркерами, что и существующие infra-тесты (требуют живой Neo4j).

---

## Шаг 5. Проверка вручную

1. Очистить Neo4j: `MATCH (n) DETACH DELETE n` + `DROP CONSTRAINT ...` (или пересоздать контейнер).
2. Запустить `uvicorn api.main:app --reload` → в логах увидеть `Schema up to date: 12 constraints, 4 indexes`.
3. В Neo4j Browser: `SHOW CONSTRAINTS` → 12 штук.
4. Перезапустить → второе применение не падает, логи чистые.
5. Запустить `python scripts/seed.py` → данные грузятся без дубликатов.
6. Остановить Neo4j, запустить FastAPI → стартует в degraded, в логах warning про пропущенную миграцию, без exception.

---

## Шаг 6. Обновить `CLAUDE.md`

В секцию **Key architectural decisions** добавить пункт:
> **Schema migrations are auto-applied on startup.** `SchemaMigrator` runs after `connect_with_retry` in lifespan. `scripts/migrate.py` остаётся для ручного запуска (CI, deploy hooks). Список constraints/indexes — единственный источник истины — в `core/database/migrations.py`.

В секцию **Project structure** добавить строку про `core/database/migrations.py`.

---

## Чего НЕ делаем на этом шаге

- Версионирование (schema_version узел) — добавим, когда появятся миграции данных, а не только DDL.
- Distributed lock для multi-pod деплоя — пока один инстанс.
- Auto-rollback — `IF NOT EXISTS` + идемпотентность покрывают 100% текущих сценариев.
- Вызов из `seed.py` — seed остаётся независимым; гарантия порядка через docker-compose / документацию.

---

## Файлы, которые меняются

| Файл | Действие |
|---|---|
| `core/database/migrations.py` | **новый** — `SchemaMigrator` + `CONSTRAINTS`/`INDEXES` |
| `scripts/migrate.py` | переписан в обёртку (~20 строк) |
| `api/main.py` | +2 строки в lifespan |
| `tests/test_migrations.py` | **новый** — 3 теста |
| `CLAUDE.md` | +1 архитектурное решение, +1 строка в structure |

**Оценка:** 1–1.5 часа с тестами и ручной проверкой.
