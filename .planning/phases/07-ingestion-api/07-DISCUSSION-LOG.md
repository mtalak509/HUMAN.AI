# Phase 7: Ingestion API - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in 07-CONTEXT.md — this log preserves the discussion.

**Date:** 2026-06-14
**Phase:** 07-ingestion-api
**Mode:** discuss (interactive, default)
**Response language:** Russian (по запросу пользователя в ходе выбора областей)
**Areas discussed:** Status tracking, Duplicate handling, Failure & retry
**Area not selected:** POST flow & document_id (решено вытекающе из статус-решения, см. D Claude's Discretion)

## Gray areas presented

| Area | Selected |
|------|----------|
| Status tracking | ✅ |
| POST flow & document_id | ❌ (не выбрана; решена вытекающе) |
| Duplicate handling | ✅ |
| Failure & retry | ✅ |

## Q&A

### Status tracking

**Q1 — Набор статусов пайплайна.**
Опции: (a) `queued→parsing→extracting→writing→written + failed` (из ROADMAP, рекомендовано);
(b) `queued→parsing→extracting→resolving→written + failed` (из §5.7); (c) минимум
`queued→processing→written + failed`.
→ **Выбор: (c) минимум.** (Вопреки рекомендации — founder's call.) Зафиксировано отклонение
от success criterion #2 (D-02).

**Q2 — Кто создаёт Document(queued).**
Опции: (a) POST синхронно MERGE'ит Document(queued) [рекоменд.]; (b) Celery-таск первым делом;
(c) отдельное хранилище в Redis.
→ **Выбор: (a) POST синхронно.** (D-04; попутно решает POST-flow область.)

### Duplicate handling

**Q1 — Повторный POST того же PDF.**
Опции: (a) умно по статусу (written→вернуть, failed→перезапуск, in-flight→текущий) [рекоменд.];
(b) всегда перезапускать; (c) 409 Conflict.
→ **Выбор: (a) умно по статусу.** (D-05.)

### Failure & retry

**Q1 — Хранение деталей ошибки.**
Опции: (a) поля `error` + `failed_stage` на Document [рекоменд.]; (b) одно поле `error`;
(c) только в логах.
→ **Выбор: (a) error + failed_stage.** (D-06.)

**Q2 — Политика ретраев.**
Опции: (a) fail-fast без авторетрая [рекоменд.]; (b) авторетрай только транзиентных;
(c) авторетрай любых.
→ **Выбор: (a) fail-fast.** (D-07; внутренний 1-retry экстрактора сохраняется.)

## Deferred ideas captured
- Пер-этапные статусы; Celery autoretry транзиентных; `POST /search` (v1.3);
  entity resolution между документами (v1.2); bulk/батч-загрузка ~300 резюме.

## Notes / flags raised by Claude
- D-02: минимальный набор статусов противоречит ROADMAP success criterion #2 — планировщик
  должен скорректировать критерий проверки.
- Specifics: Neo4j-недоступность для шага write должна давать `failed`, а не немой
  graceful-degradation парсера.
