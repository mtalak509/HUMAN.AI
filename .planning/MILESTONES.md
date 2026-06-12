# Milestones: HUMAN.AI

## v1.0 — Инфраструктура и онтология

**Статус:** ✓ Завершён (2026-05-07)
**Фазы:** 1–3 (9 планов)

**Что вошло:**
- FastAPI + Docker Compose + Neo4j/Qdrant/Redis
- 12 Pydantic-моделей онтологии + Cypher-миграции
- Seed-кандидат c-001, scripts/queries.py, smoke-тесты
- R&D smoke-test экстрактора (5 резюме, зелёный, вне GSD-фаз)

**Критерий выхода выполнен:** `docker compose up -d` поднимает стек, в Neo4j лежит кандидат, `pytest tests/test_infra.py` зелёный.

---

## v1.1 — Ingestion Pipeline

**Статус:** ◆ В разработке (начат 2026-06-03)
**Фазы:** 4–7 (9 планов)

**Цель:** PDF-резюме через API → кандидат в Neo4j-графе без ручного ввода.

**Критерий выхода:** `POST /documents` с реальным PDF → через несколько секунд Candidate в графе с Skills, Experience, Education, Contacts, Facts. `find_candidates_by_skill()` находит нового кандидата.
