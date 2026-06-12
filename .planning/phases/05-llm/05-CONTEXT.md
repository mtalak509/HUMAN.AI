# Phase 5: LLM-экстрактор - Context

**Gathered:** 2026-06-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Система принимает plain text резюме (`ParseResult.extracted_text` + `document_id` из Фазы 4) и возвращает `ExtractedCandidate` — валидированный Pydantic-объект с данными кандидата, извлечёнными через LLM. Перенос `rnd/src/openrouter_client.py` в `core/extractor/` с адаптацией под паттерны `core/` (async, config-driven).

**Out of scope:** нормализация в ноды графа (Company/Role/Skill как отдельные узлы, Fact-провенанс, Cypher MERGE) — это Фаза 6 (Graph Writer). Entity resolution / дедупликация — v1.2.
</domain>

<decisions>
## Implementation Decisions

### Sync vs async API
- **D-01:** `Extractor.extract(text, document_id)` — **async**. Синхронный вызов OpenAI SDK оффлоудится через `loop.run_in_executor(None, ...)` — ровно как `PdfParser.parse()` (Фаза 4). Чисто встаёт в async/Celery-пайплайн Фазы 7. Не копируем синхронный rnd-клиент как есть.

### Провенанс (document_id, model_version)
- **D-02:** `document_id` и `model_version` — **top-level поля на `ExtractedCandidate`**, не per-claim. Фаза 6 (Graph Writer) штампует каждый `Fact`-узел из этих двух значений. Удовлетворяет success-критерий #5 без преждевременного дублирования провенанса на каждом experience/skill.
- **D-03:** `model_version` = строковый id модели, фактически использованной для вызова (напр. `qwen/qwen3.6-plus`), фиксируется в момент extract().

### Schema ExtractedCandidate
- **D-04:** Сохраняем **проверенную rnd-схему `Resume` дословно** по полям: `full_name`, `contacts[{type, value}]`, `experiences[{from_date, to_date, company, role, description, skills_mentioned}]`, `education[{institution, degree, field, from_date, to_date}]`, `skills[]`. Класс переименовывается в `ExtractedCandidate`. Обоснование: 0 ValidationError на 5 резюме (`rnd/smoke_test_findings.md`) — не ломаем то, что работает.
- **D-05:** Экстрактор **выводит `is_current` на каждом experience** (`is_current = to_date is None`). Это единственная дельта-нормализация в Фазе 5; `is_current` есть в онтологии (`Experience.is_current`) и нужен Фазе 6.
- **D-06:** Поверх rnd-схемы добавляются только провенанс-поля из D-02. Переименование под имена онтологии (company→Company.name и т.д.) НЕ делаем — это маппинг Фазы 6.

### Carried forward (заблокировано ранее — не пере-обсуждать)
- **json_object + Pydantic-валидация + 1 retry** — дефолт экстрактора (CLAUDE.md, `rnd/smoke_test_findings.md`: 0 ошибок на 5 резюме). `response_format=json_schema` отвергнут (систематически роняет summary `skills`).
- **`OPENROUTER_API_KEY` уже в `Settings`** (добавлен в Фазе 4) — читать оттуда, не из `os.getenv`.

### Claude's Discretion
- **Config-поля в `Settings`** (паттерн `storage_root` из Фазы 4): `extractor_model` (default — модель из smoke-test), `openrouter_base_url` (default `https://openrouter.ai/api/v1`), `extractor_timeout`, опц. `extractor_temperature` (default 0). `api_key` из `Settings.openrouter_api_key`. Точный набор знобов — на планировании.
- **Failure-policy при провале 2-го retry** (ValidationError на повторе): склоняюсь к **propagate exception** (Фаза 7 пометит документ status=failed) — ошибка извлечения ≠ инфра-outage, тихий sentinel неуместен. Финализировать на планировании.
- Формулировка PROMPT_TEMPLATE и retry-prompt — переносятся из rnd как есть.
- `ExtractedCandidate` как `pydantic.BaseModel` (валидированный выход LLM), а не frozen dataclass.
</decisions>

<specifics>
## Specific Ideas

- «Перенос, а не переписывание»: `OpenRouterClient.extract_resume()` (json_object + 1 retry) — это эталон логики; меняем только обвязку (async, Settings, провенанс), не саму стратегию вызова.
- Эквивалентность результатов проверяется против `rnd/data/results/*.parsed.json` на тех же 5 резюме (success-критерий #4).
</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Архитектура и онтология
- `core_architecture.md` — общая архитектура, онтология, Fact-провенанс (CLAUDE.md: читать перед структурными решениями)
- `core/schemas/models.py` — 12 типов узлов онтологии (для awareness маппинга в Фазе 6: Experience.is_current, Company.name, Role.title, Skill.name, Fact.model_version)

### Задел экстрактора (перенос)
- `rnd/src/openrouter_client.py` — исходная логика: `extract_resume()` json_object + 1 retry, PROMPT_TEMPLATE, `_build_prompt`. Переносится в `core/extractor/llm.py`.
- `rnd/src/json_schema.py` — проверенная схема `Resume` (Contact/Experience/Education) → база `ExtractedCandidate` в `core/extractor/schema.py`.
- `rnd/smoke_test_findings.md` — почему json_object, а не json_schema; baseline на 5 резюме.
- `rnd/data/results/*.parsed.json` — эталонные выходы для сверки (критерий #4).

### Решения проекта
- `CLAUDE.md` — решение «LLM extractor: prefer json_object over json_schema»; конвенции (Loguru {} placeholders, Settings cached / cache_clear в тестах, scripts/код используют `get_settings()`).
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `rnd/src/openrouter_client.py::OpenRouterClient.extract_resume` — json_object + retry-on-ValidationError; переносится почти 1:1 (плюс async-обвязка).
- `rnd/src/json_schema.py::Resume` (+ Contact/Experience/Education) — схема для `ExtractedCandidate`.
- `core/parser/pdf.py::PdfParser.parse` — эталон async + `run_in_executor` для синхронной библиотеки (D-01).
- `core/config.py::Settings` — `get_settings()` lru_cache; `openrouter_api_key` уже есть; паттерн добавления config-поля (`storage_root`).

### Established Patterns
- Async-методы оффлоудят синхронный I/O через `loop.run_in_executor` (Фаза 4).
- Config-driven через `Settings` + `get_settings()`; код/скрипты зовут напрямую, не через DI.
- Loguru с позиционными `{}` (никогда f-strings в logger).
- Pydantic v2; валидация выхода LLM + 1 retry.

### Integration Points
- **Вход:** `ParseResult.extracted_text` + `document_id` (Фаза 4).
- **Выход:** `ExtractedCandidate` → потребитель Фаза 6 (Graph Writer) превращает поля в узлы + Fact-узлы, штампованные `document_id`/`model_version` (D-02).
- **Структура модуля:** `core/extractor/schema.py` (ExtractedCandidate), `core/extractor/llm.py` (Extractor class), `core/extractor/__init__.py` (re-export) — по аналогии с `core/parser/`.
</code_context>

<deferred>
## Deferred Ideas

- Нормализация в граф (Company/Role/Skill как узлы, Fact-провенанс, Cypher MERGE) — **Фаза 6**.
- json_schema + post-processing (`skills ∪= union(experiences[*].skills_mentioned)`) как гипотеза полноценного R&D — вне скопа (CLAUDE.md).
- Entity resolution / дедупликация кандидатов — **v1.2**.
- Мульти-модельный A/B и golden-set на 20+ резюме (полноценный R&D) — пропущен по решению проекта.
</deferred>

---

*Phase: 05-llm*
*Context gathered: 2026-06-11*
