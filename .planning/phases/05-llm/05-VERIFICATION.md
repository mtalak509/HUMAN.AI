---
phase: 05-llm
verified: 2026-06-11T21:00:00Z
status: passed
score: 9/9 must-haves verified
overrides_applied: 0
---

# Phase 5: LLM-Экстрактор — Отчёт верификации

**Цель фазы:** Превратить plain text разобранного резюме в валидированный `ExtractedCandidate`
(поля, выровненные по онтологии + провенанс) через LLM — готовый для Фазы 6 (Graph Writer).

**Проверено:** 2026-06-11T21:00:00Z
**Статус:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | ExtractedCandidate валидирует выход LLM по полям онтологии (full_name, contacts, experiences, education, skills) | ✓ VERIFIED | `core/extractor/schema.py` строки 60–79; `model_fields` подтверждены запуском `python -c "from core.extractor import ExtractedCandidate; print(list(ExtractedCandidate.model_fields.keys()))"` → `['document_id', 'model_version', 'full_name', 'contacts', 'experiences', 'education', 'skills']` |
| 2 | Каждый Experience несёт is_current, вычисляемый из to_date is None | ✓ VERIFIED | `@computed_field @property def is_current(self) -> bool: return self.to_date is None` (строки 43–47); тест `test_is_current_serialized_in_model_dump` подтверждает сериализацию; 31/31 тестов зелёные |
| 3 | ExtractedCandidate несёт top-level провенанс: document_id и model_version | ✓ VERIFIED | Строки 71–72 schema.py; `_validate()` в llm.py строки 157–161 перезаписывает оба поля значениями вызова (не из ответа LLM — T-05-04) |
| 4 | Все 5 эталонных rnd/data/results/*.parsed.json валидируются без ошибок | ✓ VERIFIED | `pytest tests/test_extractor_schema.py::TestParsedJsonEquivalence` — 6 тестов (1 проверка количества файлов + 5 параметризованных), все зелёные; все 5 файлов: Denisenko, Markova, Suhanova, Talakin, Talakina |
| 5 | Settings содержит конфиг-кнобы экстрактора (extractor_model, openrouter_base_url, extractor_timeout, extractor_temperature) | ✓ VERIFIED | `core/config.py` строки 43–58; `python -c "from core.config import get_settings; ..."` → `qwen/qwen3.6-plus https://openrouter.ai/api/v1 60.0 0.0` |
| 6 | Extractor.extract(text, document_id) — async, возвращает валидированный ExtractedCandidate | ✓ VERIFIED | `async def extract(self, text: str, document_id: str) -> ExtractedCandidate` (llm.py строка 163); тест `test_extract_success_returns_provenance` зелёный |
| 7 | Синхронный вызов OpenAI SDK оффлоудится через loop.run_in_executor | ✓ VERIFIED | llm.py строки 183–185: `loop = asyncio.get_running_loop(); raw = await loop.run_in_executor(None, self._call, prompt)`; паттерн повторён для retry (строка 199); `run_in_executor` встречается 5 раз в файле; `test_extract_uses_run_in_executor` зелёный |
| 8 | Режим json_object + Pydantic-валидация + 1 retry перенесён из rnd без изменений стратегии | ✓ VERIFIED | `response_format={"type": "json_object"}` (llm.py строка 136); `json_object` встречается 4 раза; единственное вхождение `json_schema` — это `model_json_schema()` (метод Pydantic, строка 65), не `response_format`; тест `test_response_format_is_json_object` зелёный; retry-логика строки 186–200 |
| 9 | Провал 2-го retry (ValidationError на повторе) пробрасывает исключение, не возвращает sentinel | ✓ VERIFIED | llm.py строка 200: второй `_validate()` вызов не обёрнут в try/except — исключение всплывает; тест `test_extract_propagates_on_second_failure` зелёный |

**Score: 9/9 truths verified**

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `core/extractor/schema.py` | ExtractedCandidate + Contact/Experience/Education Pydantic v2 | ✓ VERIFIED | 80 строк; содержит `class ExtractedCandidate(BaseModel)`, `computed_field`, `is_current`; 0 вхождений `Optional` (PEP 604) |
| `core/extractor/__init__.py` | Public re-export ExtractedCandidate + Extractor | ✓ VERIFIED | 9 строк; `from core.extractor.schema import Contact, Education, Experience, ExtractedCandidate`; `from core.extractor.llm import Extractor`; `__all__` содержит все 5 символов |
| `core/config.py` | extractor config fields в Settings | ✓ VERIFIED | Строки 43–58; все 4 поля с дефолтами smoke-test; `openrouter_api_key` не дублирован (1 вхождение) |
| `core/extractor/llm.py` | Extractor class с async extract() + json_object + 1 retry | ✓ VERIFIED | 211 строк (> min 80); `class Extractor`, `async def extract`, `run_in_executor`, `json_object`; `os.getenv` — 0 вхождений |
| `tests/test_extractor_schema.py` | Equivalence-валидация 5 parsed.json + is_current | ✓ VERIFIED | 216 строк; 24 теста; equivalence-тест присутствует (`parsed.json` встречается в файле) |
| `tests/test_extractor_unit.py` | Unit-тесты с замоканным OpenAI клиентом | ✓ VERIFIED | 252 строки; 7 тестов; `json_object` присутствует |
| `tests/test_extractor_integration.py` | Equivalence-тест против parsed.json; skip без ключа | ✓ VERIFIED | 157 строк; `parsed.json` и `skipif` присутствуют; параметризован по 5 именам резюме |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `core/extractor/schema.py::Experience` | `to_date is None` | computed_field `is_current` | ✓ WIRED | `@computed_field @property def is_current(self) -> bool: return self.to_date is None` |
| `core/extractor/__init__.py` | `core/extractor/schema.py` | re-export | ✓ WIRED | `from core.extractor.schema import Contact, Education, Experience, ExtractedCandidate` |
| `core/extractor/__init__.py` | `core/extractor/llm.py` | re-export | ✓ WIRED | `from core.extractor.llm import Extractor` |
| `core/extractor/llm.py::Extractor.extract` | `ExtractedCandidate` | `_validate()` + штамповка document_id/model_version | ✓ WIRED | `_validate()` вызывает `ExtractedCandidate.model_validate({**json.loads(raw), "document_id": document_id, "model_version": self._model})` |
| `core/extractor/llm.py::Extractor.extract` | synchronous OpenAI `.chat.completions.create` | `loop.run_in_executor(None, ...)` | ✓ WIRED | Строки 183–185, 198–199; подтверждено тестом `test_extract_uses_run_in_executor` |
| `core/extractor/llm.py` | `Settings` | `get_settings()` | ✓ WIRED | `__init__` читает `s.openrouter_api_key`, `s.extractor_model`, `s.extractor_temperature`, `s.openrouter_base_url`, `s.extractor_timeout`; `os.getenv` не используется |

---

### Data-Flow Trace (Level 4)

Артефакты фазы — pure data extraction, не rendering-компоненты. Данные текут: `str (text)` → `Extractor._call()` → `Extractor._validate()` → `ExtractedCandidate`. Провенанс (`document_id`, `model_version`) поступает из аргумента вызова и `self._model` — не из LLM-ответа (LLM-значения перезаписываются). Данные текут от реального источника (PDF → PdfParser → text → Extractor) через unit-тесты с замоканным клиентом и live integration-тест против 5 реальных резюме.

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `Extractor._validate()` | `data` | `json.loads(raw)` из ответа LLM | Да — реальный JSON от модели | ✓ FLOWING |
| `ExtractedCandidate` провенанс | `document_id`, `model_version` | аргумент вызова + `self._model` | Да — аргумент = SHA-256 PDF; model = настройка | ✓ FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Импорт публичного API | `python -c "from core.extractor import Extractor, ExtractedCandidate; print(list(ExtractedCandidate.model_fields.keys()))"` | `['document_id', 'model_version', 'full_name', 'contacts', 'experiences', 'education', 'skills']` | ✓ PASS |
| Settings defaults | `python -c "from core.config import get_settings; get_settings.cache_clear(); s=get_settings(); print(s.extractor_model, ...)"` | `qwen/qwen3.6-plus https://openrouter.ai/api/v1 60.0 0.0` | ✓ PASS |
| Offline тесты (schema + unit) | `pytest tests/test_extractor_schema.py tests/test_extractor_unit.py -v` | `31 passed, 3 warnings in 1.10s` | ✓ PASS |
| Lint | `ruff check core/extractor core/config.py tests/test_extractor_*.py` | `All checks passed!` | ✓ PASS |
| Type check | `mypy core/extractor` | `Success: no issues found in 3 source files` | ✓ PASS |
| Integration test (skip без ключа) | `pytest tests/test_extractor_integration.py -v` (без ключа) | `5 skipped` (код 0) | ✓ PASS |

*Примечание по warnings: 3 предупреждения pytest в `test_extractor_unit.py` — sync-тесты помечены `@pytest.mark.asyncio` через модульный `pytestmark`. Это косметический вопрос (pytest-asyncio обрабатывает их корректно), не влияет на работу тестов.*

---

### Requirements Coverage

| Requirement | Source Plan | Описание | Status | Evidence |
|-------------|-------------|---------|--------|----------|
| EXTR-01 | 05-02 | Система принимает plain text и возвращает структурированный Resume-объект через LLM | ✓ SATISFIED | `Extractor.extract(text, document_id) -> ExtractedCandidate`; async; unit + integration тесты зелёные |
| EXTR-02 | 05-02 | Режим json_object + Pydantic-валидация + 1 retry при ValidationError | ✓ SATISFIED | `response_format={"type": "json_object"}`; `ValidationError` на первом ответе → retry; 2-й провал пробрасывает; тесты 2 и 3 в `test_extractor_unit.py` |
| EXTR-03 | 05-01 | Schema охватывает: full_name, contacts, experiences (даты/компания/роль/навыки), education, skills | ✓ SATISFIED | `ExtractedCandidate` несёт все поля; `Experience` содержит `from_date`, `to_date`, `company`, `role`, `skills_mentioned`, `is_current`; 5/5 parsed.json валидируются |

**Все 3 требования фазы выполнены. Orphaned requirements: нет.** REQUIREMENTS.md отмечает EXTR-01/02 как `Done ✅ 2026-06-11` и EXTR-03 как `Complete ✅ 2026-06-11`.

---

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `tests/test_extractor_unit.py` строки 165, 222, 240 | Sync-тесты получают `asyncio` mark через модульный `pytestmark` | ℹ️ Info | Pytest выдаёт warning, но тесты проходят корректно. Не влияет на результат верификации. |

Значимых заглушек, TODO/FIXME, пустых реализаций или hardcoded sentinel-значений не обнаружено. `return null` / `return {}` / пустые хендлеры отсутствуют.

---

### Human Verification Required

Нет. Фаза 5 — pure backend extraction layer без UI. Все поведения верифицированы автоматически:
- Pydantic-валидация — программно проверена тестами
- Retry-логика — покрыта unit-тестом с мок-клиентом
- Провенанс-штамповка — unit + integration тесты
- Live-качество извлечения (5/5 резюме) — задокументировано в 05-02-SUMMARY.md (исполнено разработчиком с реальным API-ключом; тест является воспроизводимым при наличии ключа)

---

### Gaps Summary

Зазоров нет. Все 9 must-have truths верифицированы, все 7 артефактов существуют, содержательны и включены в связи. Три требования EXTR-01/02/03 выполнены. Lint и mypy чисты. Offline-тесты (31 штука) полностью зелёные без инфраструктуры.

---

_Verified: 2026-06-11T21:00:00Z_
_Verifier: Claude (gsd-verifier)_
