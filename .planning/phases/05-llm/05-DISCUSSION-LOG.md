# Phase 5: LLM-экстрактор - Discussion Log

> **Audit trail only.** Не использовать как вход для планирования/исполнения. Решения — в CONTEXT.md.

**Date:** 2026-06-11
**Phase:** 05-llm
**Mode:** discuss (standard)
**Areas selected:** Sync vs async API, Провенанс, Schema-выравнивание (Config+failure-policy — не выбрана → Claude's Discretion)

## Carried forward (не обсуждалось)
- json_object + Pydantic + 1 retry (CLAUDE.md / smoke findings) — заблокировано.
- OPENROUTER_API_KEY уже в Settings (Фаза 4).

## Questions & Answers

### Sync vs async API
- Options: Async (run_in_executor, как PdfParser) [рек.] | Sync (как rnd)
- **Выбор:** Async (run_in_executor) → D-01

### Провенанс (document_id + model_version)
- Options: Top-level на ExtractedCandidate [рек.] | Per-claim
- **Выбор:** Top-level на ExtractedCandidate → D-02/D-03

### Schema ExtractedCandidate
- Options: rnd-схема + is_current [рек.] | Переименовать под онтологию | rnd-схема 1:1
- **Выбор:** rnd-схема + is_current → D-04/D-05/D-06

## Claude's Discretion (зафиксировано)
- Config-поля (model/base_url/timeout/temperature) из Settings — паттерн storage_root.
- Failure-policy при провале 2-го retry: склонность к propagate exception; финал на планировании.

## Deferred
- Граф-нормализация + Fact → Фаза 6.
- json_schema + post-processing → вне скопа.
- Entity resolution → v1.2.
