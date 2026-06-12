# Phase 6: Graph Writer - Discussion Log

> **Audit trail only.** Not consumed by downstream agents. Decisions live in 06-CONTEXT.md.

**Date:** 2026-06-12
**Phase:** 06-graph-writer
**Mode:** discuss (text / remote `/rc`)
**Areas discussed:** ID-деривация, Fact.confidence, Fact-scope, Skill-источник, Конфликты/scope

## Areas & Selections

### 1. ID-деривация и идемпотентность
- Options: 1a детерминированные ID из содержимого / 1b candidate_id=sha1(full_name) / 1c custom
- **Selected: 1a** — candidate_id = document_id; experience/education/contact/fact id = sha1(composite).
- Rationale: «каждое резюме = новый кандидат» (без entity resolver v1.1); полный детерминизм → WRITE-04.

### 2. Fact.confidence
- Options: 2a const 1.0 / 2b null / 2c 0.9
- **Selected: 2b** — `confidence = null`.
- Rationale: экстрактор confidence не отдаёт; не выдумываем значение, калибровка — позже.

### 3. Объём Fact-провенанса
- Options: 3a Fact на skill+experience / 3b Fact на всё (incl. education, contacts) / 3c custom
- **Selected: 3a** — Fact только на skills (has_skill) и experiences (worked_at);
  Education/Contact — узлы без Fact (как seed.py).

### 4. Источник и обработка Skill (deep-dive)
- **4.1 union:** объединяем `skills` ∪ `experiences[*].skills_mentioned`. Selected.
- **4.2 нормализация:** Options 4.2a strip+exact dedupe (канонизация отложена) / 4.2b lowercase в v1.1.
  **Selected: 4.2a.**
- **4.3 ребро Experience→Skill:** Options 4.3a без нового ребра (только Candidate-level HAS_SKILL) /
  4.3b добавить `Experience-[:USED_SKILL]->Skill`. **Selected: 4.3b** (явный выбор пользователя
  добавить ребро).
- **4.4 Fact для навыков:** Options 4.4 один has_skill-Fact на уникальный навык (рёбра денорм,
  без per-edge Fact) / 4.4-rich per-USED_SKILL Fact. **Selected: 4.4** (после уточнения).

### 5. Конфликты / мульти-документ (scope)
- Options: 5a только идемпотентность того же документа (cross-doc → v1.2) / 5b is_current-конфликты
  уже в v1.1 / 5c custom
- **Selected: 5a** — cross-document conflict resolution отложено в v1.2.

## Corrections / Notes
- По области 4 пользователь отклонил рекомендацию 4.3a в пользу 4.3b (добавить ребро USED_SKILL) —
  это вводит новый тип ребра вне текущей онтологии/seed; constraint не требуется.

## Deferred Ideas Captured
- Канонизация навыков (canonical_name/category, lowercase, синонимы) → v1.2.
- Entity resolution + cross-document Fact-конфликты (is_current) → v1.2.
- Confidence-калибровка Fact'ов → будущая фаза.
- Provenance на денорм-рёбра (used_skill_in-Fact) → избыточно для v1.1.
