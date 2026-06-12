# Phase 6: Graph Writer - Context

**Gathered:** 2026-06-12
**Status:** Ready for planning

<domain>
## Phase Boundary

`GraphWriter.write(candidate: ExtractedCandidate, document_id: str)` записывает полный
граф одного кандидата в Neo4j через `MERGE`:

- **Узлы:** Candidate, Contact, Skill, Experience, Company, Role, Education.
- **Провенанс:** `Fact`-узлы со связями `Candidate-[:HAS_FACT]->Fact`,
  `Fact-[:EXTRACTED_FROM]->Document`, `Fact-[:SUPPORTS]->(Skill|Experience)`.
- **Денормализация:** прямые связи `Candidate-[:HAS_SKILL]->Skill`,
  `Candidate-[:HAS_EXPERIENCE]->Experience`, `Experience-[:AT_COMPANY]->Company`,
  `Experience-[:AS_ROLE]->Role`, `Candidate-[:HAS_EDUCATION]->Education`,
  `Candidate-[:HAS_CONTACT]->Contact`.
- **Идемпотентно:** повторный `write()` того же документа не плодит узлов (WRITE-04).

Входной объект — `ExtractedCandidate` (resume-shaped, БЕЗ id и БЕЗ confidence), а НЕ
`ExtractedFact[]` из §5.4 архитектуры (отклонение D-06 фазы 5 — маппинг резолвится здесь).

Покрывает требования **WRITE-01…WRITE-04**. Узлы `Vacancy / Status / HRNote / Document`
writer НЕ создаёт (не из резюме; Document уже создан парсером в фазе 4).

**Вне границы (другие фазы):** entity resolution / дедуп кандидатов (v1.2),
HTTP/Celery-слой (фаза 7), канонизация навыков.

</domain>

<decisions>
## Implementation Decisions

### ID-деривация и идемпотентность (драйвер WRITE-04)
- **D-01:** Все ID детерминированы из содержимого (у `ExtractedCandidate` своих id нет):
  - `candidate_id = document_id` — 1 резюме = 1 кандидат (согласовано с «без entity
    resolver в v1.1», см. core_architecture.md стр. 302 и STATE.md).
  - `experience_id = sha1(f"{document_id}|{company}|{role}|{from_date}")`
  - `education_id  = sha1(f"{document_id}|{institution}|{from_date}")`
  - `contact_id    = sha1(f"{document_id}|{type}|{value}")`
  - `fact_id       = sha1(f"{document_id}|{predicate}|{value}")`
  - Skill/Company/Role мёрджатся по натуральным ключам (`name` / `name` / `title`) —
    БЕЗ синтетического id (constraint уже существует в migrations.py).
  - Хэш-функция и формат разделителя — на усмотрение исполнителя (sha1/sha256, главное
    детерминизм). Конкатенация полей фиксирована выше.

### Fact.confidence (открытое решение из CLAUDE.md, закрыто)
- **D-02:** `Fact.confidence = null`. Экстрактор confidence не отдаёт; поле в онтологии
  есть, но в v1.1 не заполняем (НЕ выдумываем константу). Калибровка confidence —
  будущая фаза. `Fact.model_version` берётся из `ExtractedCandidate.model_version`,
  `Fact.is_current = true`, `Fact.extracted_at = now()`.

### Объём Fact-провенанса
- **D-03:** Fact-узлы создаём только на:
  - каждый навык → `Fact{predicate:"has_skill", value:<skill_name>}`, `SUPPORTS→Skill`;
  - каждый опыт → `Fact{predicate:"worked_at", value:<company>}`, `SUPPORTS→Experience`.
  - Education и Contact: узлы и денорм-связи создаём, но **БЕЗ** Fact-узлов (как в
    `scripts/seed.py`). Минимально и осмысленно покрывает WRITE-02.

### Источник и обработка Skill
- **D-04:** Множество навыков = **union** top-level `skills` ∪ всех
  `experiences[*].skills_mentioned`. Без union теряем навыки (smoke-test: модель роняет
  часть summary-навыков, но перечисляет их в ролях — см. CLAUDE.md «json_object» findings).
- **D-05:** Перед MERGE: только `.strip()` + дедуп по точному совпадению строки.
  Регистр и канонизацию («ML»→«machine learning», lowercase) в v1.1 НЕ трогаем —
  `Skill.name` сохраняется как в резюме. Канонизация навыков отложена (см. Deferred).
- **D-06:** Добавляем ребро **`Experience-[:USED_SKILL]->Skill`** для навыков из
  `skills_mentioned` конкретной роли. Это НОВЫЙ тип ребра (в текущей онтологии/seed его
  нет; constraint не требуется — у рёбер нет uniqueness-ключей). Навык только из
  top-level `skills` (не упомянут ни в одной роли) получает `HAS_SKILL` без `USED_SKILL`.
- **D-07:** Один `has_skill`-Fact на **уникальный** навык (`SUPPORTS→Skill`,
  `EXTRACTED_FROM→Document`). Рёбра `HAS_SKILL` и `USED_SKILL` — денормализация графа
  (как в §5.1), отдельный Fact на каждое ребро НЕ создаём: провенанс навыка уже даёт
  `has_skill`-Fact, провенанс опыта — `worked_at`-Fact.

### Конфликты и мульти-документ (scope)
- **D-08:** v1.1 гарантирует только идемпотентность ПОВТОРА ТОГО ЖЕ документа
  (`MERGE` + `SET` перетирает свой же узел — паттерн фазы 4 для Document). Конфликт-
  резолюция между РАЗНЫМИ документами одного человека (новый Fact `is_current=true`,
  старый сохраняется) — это entity resolution, отложено в v1.2 (см. Deferred).

### Claude's Discretion (на усмотрение планировщика/исполнителя)
- Структура модуля: `core/writer/cypher.py` (MERGE-запросы) + `core/writer/graph_writer.py`
  (класс `GraphWriter`) — как в ROADMAP, но разбивка на планы за планировщиком.
- Транзакционная граница: обернуть весь write одного кандидата в одну
  `session.execute_write(...)` транзакцию (атомарность — без полу-записанного графа).
  Синхронность/async — следовать паттерну проекта (async Neo4j driver).
- Конкретная hash-функция (sha1 vs sha256) и точный шаблон строки внутри формата D-01.
- Точные предикаты/тексты сверх перечисленных — придерживаться значений из `seed.py`.

</decisions>

<specifics>
## Specific Ideas

- `scripts/seed.py` — эталон: в нём уже написаны все MERGE-узлы, денорм-связи и паттерн
  `Fact → HAS_FACT / EXTRACTED_FROM / SUPPORTS`. Writer воспроизводит ровно этот паттерн,
  но данные берёт из `ExtractedCandidate`, а не хардкод.
- Graceful degradation как в парсере (`core/parser/pdf.py`): guard на `db.is_connected`
  перед `session()`; при недоступном Neo4j — лог-warning, без краша.
- Идемпотентность Document уже реализована в фазе 4 через `SET` (не `ON CREATE SET`) —
  применить тот же подход к узлам кандидата, чтобы повторный write обновлял, а не плодил.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Архитектура графа и Graph Writer
- `docs/core_architecture.md` §5.1 (стр. 87–137) — паттерн Fact-узла: `HAS_FACT`,
  `EXTRACTED_FROM`, `SUPPORTS`, денормализация `HAS_SKILL`, политика конфликтов `is_current`.
- `docs/core_architecture.md` §5.4 (стр. 214–221) — Graph Writer: идемпотентность через
  `MERGE` по композитным ключам, денорм-связи для retrieval.
- `docs/core_architecture.md` §5.8 (стр. 272–276) — provenance: каждый узел/ребро
  прослеживается до `Document` через `Fact`.
- `docs/core_architecture.md` стр. 302 — «простейший Graph Writer без entity resolver,
  каждое резюме = новый кандидат».

### Контракты данных и схема
- `core/extractor/schema.py` — `ExtractedCandidate` (вход writer'а): full_name, contacts,
  experiences (company/role/from_date/to_date/skills_mentioned/is_current), education, skills,
  document_id, model_version.
- `core/schemas/models.py` — Pydantic-онтология всех 12 типов узлов (Candidate, Skill,
  Experience, Company, Role, Education, Contact, Fact, Document …).
- `core/database/migrations.py` — `CONSTRAINTS` / `INDEXES`: единственный источник истины
  по MERGE-ключам (Candidate.id, Skill.name, Company.name, Role.title, остальное `.id`).
- `scripts/seed.py` — эталонный референс MERGE-узлов, денорм-связей и Fact-провенанса.

### Интеграция и проверка
- `core/database/graph.py` — `GraphDB` (async-драйвер, `is_connected`, `session()`).
- `scripts/queries.py` — `find_candidates_by_skill/company/status`: критерий успеха #5
  (новый кандидат должен находиться этими запросами).
- `CLAUDE.md` — разделы «Fact node provenance», «MERGE keys match constraints»,
  «Extractor output is ExtractedCandidate, NOT ExtractedFact[]».

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scripts/seed.py`: готовый набор Cypher MERGE для всех узлов + Fact-паттерн — копируем
  структуру запросов, параметризуем данными из `ExtractedCandidate`.
- `core/parser/pdf.py`: паттерн graceful degradation (`is_connected` guard) и идемпотентный
  Document MERGE через `SET` — переиспользуем подход.
- `core/database/graph.py::GraphDB.session()` + `execute_write` для транзакций.
- `core/database/migrations.py`: MERGE-ключи и индексы (`fact_predicate_idx`,
  `fact_is_current_idx`, `experience_is_current_idx`) — writer должен класть поля,
  по которым уже построены индексы.

### Established Patterns
- Async Neo4j driver; синхронные участки — через `run_in_executor` (как в parser/extractor).
- Идемпотентность через `MERGE` + `SET` (обновление, не `ON CREATE SET`).
- DI через `app.state` в API; скрипты вызывают `get_settings()` напрямую (writer вызовется
  из Celery-таска фазы 7 — закладываемся на конструктор с `GraphDB`, без FastAPI DI).

### Integration Points
- Вход: `ExtractedCandidate` от `core/extractor` (фаза 5).
- Document-узел уже создан `core/parser` (фаза 4) — writer линкует Fact'ы к нему по
  `document_id`, НЕ пересоздаёт Document.
- Выход потребляется фазой 7 (Celery-таск `process_document`: parse → extract → write).
- Проверка результата — `scripts/queries.py`.

</code_context>

<deferred>
## Deferred Ideas

- **Канонизация навыков** (lowercase / синонимы «ML»↔«machine learning» / `Skill.canonical_name`
  / `category`) — v1.2. В v1.1 `name` хранится как в резюме (D-05).
- **Entity resolution / дедуп кандидатов** между разными документами + конфликт-резолюция
  фактов (`is_current` между документами) — v1.2 (D-08). Уже в реестре отложенных STATE.md.
- **Confidence-калибровка** Fact'ов — будущая фаза (D-02: пока `null`).
- **Provenance на денорм-рёбра** (`used_skill_in`-Fact на каждое USED_SKILL) — возможное
  обогащение, в v1.1 избыточно (D-07).

</deferred>

---

*Phase: 06-graph-writer*
*Context gathered: 2026-06-12*
