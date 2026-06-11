---
phase: 05-llm
plan: 01
subsystem: extractor
tags: [pydantic, schema, config, tdd]
dependency_graph:
  requires: []
  provides: [ExtractedCandidate, core.extractor.schema, extractor-config]
  affects: [core/extractor, core/config.py, tests/test_extractor_schema.py]
tech_stack:
  added: [core/extractor/]
  patterns: [computed_field, re-export shim, lru_cache settings]
key_files:
  created:
    - core/extractor/__init__.py
    - core/extractor/schema.py
    - tests/test_extractor_schema.py
  modified:
    - core/config.py
decisions:
  - D-04: rnd Resume fields переnesены дословно (Contact/Experience/Education/ExtractedCandidate)
  - D-05: Experience.is_current — computed_field из to_date is None; сериализуется в model_dump
  - D-02: ExtractedCandidate несёт top-level провенанс document_id + model_version
  - D-06: поля не переименованы под онтологию — маппинг отложен на Phase 6
  - extractor config knobs с дефолтами smoke-test (qwen/qwen3.6-plus, 60s, 0.0)
metrics:
  duration_seconds: 297
  completed_date: "2026-06-11"
  tasks_completed: 2
  tasks_total: 2
  files_created: 3
  files_modified: 1
---

# Phase 5 Plan 01: ExtractedCandidate Schema + Extractor Config Summary

**One-liner:** Pydantic v2 схема ExtractedCandidate с computed_field is_current, top-level провенансом и конфиг-кнобами экстрактора в Settings (interface-first перед Plan 05-02).

## Completed Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | ExtractedCandidate Pydantic-схема + re-export (TDD) | 92aceab | core/extractor/schema.py, core/extractor/__init__.py, tests/test_extractor_schema.py |
| 2 | Конфиг-кнобы экстрактора в Settings | 9c47c92 | core/config.py, tests/test_extractor_schema.py |

## What Was Built

### core/extractor/schema.py

Четыре Pydantic v2 модели, покрывающие контракт выхода LLM:

- `Contact` — channel (email/phone/telegram/linkedin/other) + value; Literal на type — граница доверия T-05-01.
- `Experience` — from_date/to_date/company/role/description/skills_mentioned + `is_current` как `@computed_field @property`: сериализуется в model_dump/JSON, не требуется от LLM на входе (D-05).
- `Education` — institution/degree/field/from_date/to_date; все опциональны кроме institution.
- `ExtractedCandidate` — top-level провенанс (document_id, model_version) + rnd-поля дословно (D-04). Поля не переименованы под онтологию (D-06 — маппинг в Phase 6).

Все поля используют PEP 604 (`str | None`), без `Optional`.

### core/extractor/__init__.py

Re-export shim: `from core.extractor.schema import Contact, Education, Experience, ExtractedCandidate`. Plan 05-02 добавит сюда `Extractor`.

### core/config.py (дополнение)

Четыре новых поля в `Settings` рядом с `openrouter_api_key`:
- `extractor_model = "qwen/qwen3.6-plus"` (env EXTRACTOR_MODEL)
- `openrouter_base_url = "https://openrouter.ai/api/v1"` (env OPENROUTER_BASE_URL)
- `extractor_timeout = 60.0` (env EXTRACTOR_TIMEOUT)
- `extractor_temperature = 0.0` (env EXTRACTOR_TEMPERATURE)

`openrouter_api_key` не дублирован (1 вхождение).

### tests/test_extractor_schema.py

24 теста в TDD-стиле (RED → GREEN):
- Contact type validation (Literal + invalid)
- Experience.is_current в обоих состояниях + сериализация в model_dump
- Education минимальный + полный вариант
- ExtractedCandidate: провенанс, пустые списки по умолчанию, набор полей
- Equivalence: все 5 `rnd/data/results/*.parsed.json` валидируются без ошибок
- Settings extractor defaults с cache_clear()

## TDD Gate Compliance

| Gate | Commit | Message prefix |
|------|--------|----------------|
| RED | e6f2c72 | `test(05-01):` — failing tests |
| GREEN | 92aceab | `feat(05-01):` — implementation |
| GREEN 2 | 9c47c92 | `feat(05-01):` — Settings config |

RED gate: тест упал с `ModuleNotFoundError: No module named 'core.extractor.schema'` — подтверждено.
GREEN gate: 19 тестов прошли сразу; Task 2 добавил ещё 5 тестов (24 итого).

## Verification Results

```
pytest tests/test_extractor_schema.py       → 24 passed
ruff check core/extractor core/config.py    → All checks passed
mypy core/extractor                         → Success: no issues found in 2 source files
python -c "from core.extractor import ExtractedCandidate; ..."
  → ['document_id', 'model_version', 'full_name', 'contacts', 'experiences', 'education', 'skills']
python -c "from core.config import get_settings; print(get_settings().extractor_model)"
  → qwen/qwen3.6-plus
```

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — this plan defines a pure data schema with no UI/rendering.

## Threat Flags

No new security surface introduced. T-05-01 mitigation applied: Literal on Contact.type, required company/role on Experience — Pydantic rejects malformed LLM output at the schema boundary. T-05-02: openrouter_api_key not logged or serialised in this plan. T-05-03: accepted.
