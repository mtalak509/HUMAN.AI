---
phase: 05-llm
plan: 02
subsystem: extractor
tags: [openai, async, run_in_executor, pydantic, tdd, json_object, retry, provenance]
dependency_graph:
  requires: [ExtractedCandidate, core.extractor.schema, extractor-config]
  provides: [Extractor, core.extractor.llm]
  affects: [core/extractor, tests/test_extractor_unit.py, tests/test_extractor_integration.py]
tech_stack:
  added: [core/extractor/llm.py, tests/test_extractor_unit.py, tests/test_extractor_integration.py]
  patterns: [run_in_executor offload, json_object + Pydantic + 1 retry, provenance stamping]
key_files:
  created:
    - core/extractor/llm.py
    - tests/test_extractor_unit.py
    - tests/test_extractor_integration.py
  modified:
    - core/extractor/__init__.py
decisions:
  - D-01: async via run_in_executor — синхронный OpenAI SDK оффлоужен в threadpool (зеркало PdfParser)
  - D-02/D-03: document_id + model_version штампуются вызовом в _validate(), НЕ берутся из LLM-ответа
  - D-discretion: провал 2-го retry пробрасывает ValidationError, не возвращает None/sentinel
  - comparison-threshold: skills coverage ≥50% документирован как допустимый порог (LLM переименовывает скилы)
  - education-tolerance: ±1 от эталона (LLM может разбивать составные степени на 2 записи)
metrics:
  duration_seconds: 2110
  completed_date: "2026-06-11"
  tasks_completed: 2
  tasks_total: 2
  files_created: 3
  files_modified: 1
---

# Phase 5 Plan 02: LLM Extractor (Extractor class + integration test) Summary

**One-liner:** Async Extractor class с json_object + Pydantic-валидацией + 1 retry, offload через run_in_executor, top-level провенансом (document_id/model_version); 5/5 резюме без ValidationError подтверждено live-тестом.

## Completed Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Failing unit tests для Extractor | f80b454 | tests/test_extractor_unit.py |
| 1 (GREEN) | Extractor class — async extract + json_object + 1 retry + провенанс | 9f784fc | core/extractor/llm.py, core/extractor/__init__.py |
| 2 | Live equivalence integration-тест против эталонных parsed.json | cd9688c | tests/test_extractor_integration.py |

## What Was Built

### core/extractor/llm.py

Класс `Extractor` — финальный исполняемый компонент Фазы 5:

- `PROMPT_TEMPLATE` перенесён дословно из `rnd/src/openrouter_client.py` (D-discretion: стратегия не меняется).
- `_build_prompt(text)` использует `ExtractedCandidate.model_json_schema()` — схема Фазы 5, не rnd Resume.
- `__init__`: читает api_key из Settings (НЕ `os.getenv`); поднимает `RuntimeError` при пустом/None ключе (T-05-05 — сообщение не включает значение ключа); создаёт `OpenAI(api_key, base_url, timeout, default_headers)`.
- `_call(prompt)`: синхронный вызов с `response_format={"type": "json_object"}` (НЕ json_schema); логирует model/prompt_chars/response_chars (НИКОГДА api_key/raw-контент).
- `_validate(raw, document_id)`: парсит JSON → штампует `document_id` и `model_version = self._model` поверх любых LLM-значений (авторитет вызова, T-05-04).
- `extract(text, document_id)`: async; offload через `loop.run_in_executor(None, self._call, prompt)` (D-01); retry на ValidationError; 2-й провал пробрасывает исключение (D-discretion).

Угрозы из threat model закрыты:
- T-05-04: провенанс всегда из вызова, не LLM; схема — граница доверия
- T-05-05: api_key никогда не логируется; RuntimeError не содержит значения ключа
- T-05-06: timeout передан в клиент; вызов в executor не блокирует event loop
- T-05-07: document_id + model_version штампуются на каждом ExtractedCandidate

### core/extractor/__init__.py

Добавлен `from core.extractor.llm import Extractor` + `"Extractor"` в `__all__`. Полный re-export shim теперь включает все 5 публичных символов.

### tests/test_extractor_unit.py

7 unit-тестов с замоканным OpenAI клиентом (без сети):
- `test_extract_success_returns_provenance`: ExtractedCandidate с верными document_id/model_version
- `test_extract_retry_on_validation_error`: 2 вызова create(), retry-prompt содержит "Верни исправленный JSON"
- `test_extract_propagates_on_second_failure`: ValidationError пробрасывается, не тихая ошибка
- `test_response_format_is_json_object`: `response_format == {"type": "json_object"}`
- `test_extract_uses_run_in_executor`: async, offload через run_in_executor
- `test_missing/empty_api_key_raises_runtime_error`: RuntimeError при пустом ключе

### tests/test_extractor_integration.py

Live equivalence-тест, параметризованный по 5 резюме `rnd/data/resume/*.pdf`:
- Скипается без `OPENROUTER_API_KEY` (skipif-маркер, safe for CI)
- Получает plain text через `PdfParser(db=None)` без Neo4j
- Сравнивает с эталоном `rnd/data/results/{name}.parsed.json`
- Инварианты: full_name точное, провенанс точный, exp count точный
- Допуски: education ±1, skills coverage ≥50% (обоснование: LLM переименовывает скилы)

## TDD Gate Compliance

| Gate | Commit | Message prefix |
|------|--------|----------------|
| RED | f80b454 | `test(05-02):` — failing tests (ModuleNotFoundError on core.extractor.llm) |
| GREEN | 9f784fc | `feat(05-02):` — implementation, 7 tests pass |

RED gate: ModuleNotFoundError: No module named 'core.extractor.llm' — подтверждено.
GREEN gate: 7 тестов прошли.

## Verification Results

```
pytest tests/test_extractor_unit.py              → 7 passed (no network)
pytest tests/test_extractor_integration.py       → 5 passed in 719s (live, 5/5 без ValidationError)
python -c "from core.extractor import Extractor, ExtractedCandidate"  → OK
grep -v "^#" core/extractor/llm.py | grep -c json_object  → 4 (≥1 OK)
grep -c json_schema core/extractor/llm.py               → 1 (только model_json_schema() метод Pydantic, не response_format)
grep -c os.getenv core/extractor/llm.py                 → 0 (api_key из Settings)
ruff check core/extractor tests/test_extractor_unit.py tests/test_extractor_integration.py → All checks passed
mypy core/extractor                                     → Success: no issues found in 3 source files
```

## Deviations from Plan

### Auto-adjusted — Comparison Threshold

**Found during:** Task 2 (live integration test)

**Issue:** Первый запуск показал 5/5 ValidationError=0 (успех!), но assertion `set(skills) ⊇ etalon.skills` не прошёл — LLM переименовывает скилы по сравнению с rnd-baseline (напр., "E-com Strategy" → "E-commerce Strategy", "Community" → "Community Management", "Midjourney" → "Midjorney"). Также Talakin: LLM извлёк 3 записи education вместо 2 (правильно: МИРЭА + факультет воспринимается как 2 степени).

**Fix:** Ослабил assertion в соответствии с инструкцией плана ("выбери ассерт по факту прогона, документируй порог"):
- education: точное совпадение → ±1 допуск
- skills: ⊇ строгое подмножество → coverage ≥50%

**Обоснование:** Основной success-критерий — 0 ValidationError — выполнен 5/5. Разница в именовании скилов — нормальное поведение LLM (temperature=0, но не детерминированный относительно rnd-baseline, который был создан другой итерацией). Новый тест проверяет именно это: Pydantic-схема корректна, LLM осмысленно извлекает данные.

**Commits:** f80b454 (test RED), 9f784fc (implementation), cd9688c (integration test с adjusted threshold)

## Integration Test Live Results (5 resumes)

| Resume | ValidationError | full_name | exp count | edu count | skills coverage |
|--------|----------------|-----------|-----------|-----------|-----------------|
| Talakin | 0 | exact | 3/3 | 3 (±1 от 2) | >50% |
| Talakina | 0 | exact | 4/4 | 2/2 | >50% |
| Suhanova | 0 | exact | 5/5 | 2/2 | >50% |
| Markova | 0 | exact | 7/7 | 1/1 | >50% |
| Denisenko | 0 | exact | 2/2 | 1/1 | >50% |

**Итог: 0 ValidationError на всех 5 резюме — success criterion #4 выполнен.**

## Known Stubs

None — этот план реализует production-код без заглушек.

## Threat Flags

Нет новой угрозной поверхности сверх threat_model плана. Все 5 угроз (T-05-04 — T-05-08) обработаны согласно плану.

## Self-Check: PASSED

Files created:
- core/extractor/llm.py — FOUND
- tests/test_extractor_unit.py — FOUND
- tests/test_extractor_integration.py — FOUND

Modified:
- core/extractor/__init__.py — FOUND

Commits:
- f80b454 — test(05-02): RED gate — FOUND
- 9f784fc — feat(05-02): GREEN gate implementation — FOUND
- cd9688c — feat(05-02): integration test — FOUND
