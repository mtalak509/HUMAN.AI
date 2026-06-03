---
phase: 02-graph-ontology
reviewed: 2026-05-05T06:19:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - api/main.py
  - core/schemas/models.py
  - core/models.py (deleted)
  - .planning/codebase/STRUCTURE.md
findings:
  critical: 2
  warning: 2
  info: 0
  total: 4
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-05-05T06:19:00Z  
**Depth:** standard  
**Files Reviewed:** 4  
**Status:** issues_found

## Summary

Проверены изменения фазы `02-graph-ontology` в рабочем дереве: перенос моделей в `core/schemas/models.py`, удаление `core/models.py`, обновление импорта в `api/main.py`, синхронизация структуры в `.planning/codebase/STRUCTURE.md`.

Найдены два блокирующих риска: сломанная обратная совместимость импорта `core.models` и уязвимость упаковки/дистрибуции из-за namespace-подпакетов без явной конфигурации package discovery. Также выявлены предупреждения по отсутствию regression-тестов и текущему несоответствию strict mypy в затронутом API-файле.

## Critical Issues

### CR-01: [BLOCKER] Удаление `core.models` ломает импортный контракт фазы и обратную совместимость

**File:** `core/models.py:1-99 (deleted)`  
**Issue:** Модуль удален, при этом артефакты фазы `02-01` и проверочные команды опираются на `from core.models import ...` как на публичную точку входа. Фактическая проверка дает `ModuleNotFoundError: No module named 'core.models'`, что создает runtime-регрессию для существующих скриптов/интеграций, которые еще не мигрировали на новый путь.  
**Fix:**
```python
# core/models.py
"""Backward-compatible re-export for legacy imports."""

from core.schemas.models import (
    Candidate,
    Company,
    Contact,
    Document,
    Education,
    Experience,
    Fact,
    HRNote,
    Role,
    Skill,
    Status,
    Vacancy,
)

__all__ = [
    "Candidate",
    "Contact",
    "Skill",
    "Role",
    "Company",
    "Experience",
    "Education",
    "Vacancy",
    "Status",
    "HRNote",
    "Document",
    "Fact",
]
```

### CR-02: [BLOCKER] Риск `ModuleNotFoundError` в wheel/CI из-за отсутствия package discovery для namespace-подпакетов

**File:** `pyproject.toml:1-52`  
**Issue:** Канонические модули перенесены в `core/schemas` и `core/database`, но в этих подпапках нет `__init__.py`, а явная конфигурация сборки пакетов также отсутствует. Проверка `setuptools.find_packages()` возвращает только `['api', 'core', 'scripts']`, то есть `core.schemas` и `core.database` могут не попасть в дистрибутив при non-editable установке. Это может приводить к падению `api/main.py` (импорт `core.database.graph`) в окружениях, где используется wheel/обычная установка.  
**Fix:**
```python
# Option A (минимальный и надежный): добавить package markers
# core/database/__init__.py
# core/schemas/__init__.py

# Option B: явно настроить namespace package discovery в pyproject.toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["api*", "core*", "scripts*"]
```

## Warnings

### WR-01: [WARNING] Нет regression-тестов на миграцию import-пути и health-поведение

**File:** `api/main.py:8`  
**Issue:** Изменен импорт `GraphDB` на `core.database.graph`, но в `tests/` отсутствуют тесты, фиксирующие: (1) корректную загрузку приложения после рефакторинга путей; (2) поведение `/health` в connected/degraded режимах; (3) импорт моделей из нового и legacy пути. Без этого регрессии будут выявляться только в runtime.  
**Fix:** Добавить минимальный набор тестов:
- `tests/test_health.py`: `status=ok` при успешном `ping()` и `status=degraded` при `is_connected=False`/exception.
- `tests/test_models_imports.py`: smoke-тесты импортов `core.schemas.models` и `core.models` (если сохраняется compatibility shim).

### WR-02: [WARNING] Затронутый API-файл не проходит strict mypy, что скрывает типовые регрессии

**File:** `api/main.py:13,52,56,60`  
**Issue:** `mypy` на измененном файле возвращает ошибки (`no-untyped-def`, `no-any-return`, `type-arg`). Даже если эти ошибки не полностью внесены текущим diff, изменение файла без восстановления strict-типизации повышает риск незамеченных runtime-ошибок в DI/health обработчике.  
**Fix:**
```python
from collections.abc import AsyncIterator

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    ...

@app.get("/health")
async def health(db: GraphDB = Depends(get_db)) -> dict[str, str]:
    ...
```
И дополнительно типизировать `request.app.state` через `cast(...)` или вспомогательный typed container, чтобы убрать `no-any-return` в `get_settings()`/`get_db()`.

---

_Reviewed: 2026-05-05T06:19:00Z_  
_Reviewer: Claude (gsd-code-reviewer)_  
_Depth: standard_
