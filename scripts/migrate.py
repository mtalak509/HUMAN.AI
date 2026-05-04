"""
Идемпотентная миграция схемы Neo4j.

Запуск: python scripts/migrate.py

Применяет:
- UNIQUE constraints на идентификационные поля каждого типа узлов
- Indexes на поля частого поиска

Безопасен для повторного запуска (IF NOT EXISTS).
"""

import asyncio
import sys

from loguru import logger

from core.config import get_settings
from core.graph import GraphDB

# ---------------------------------------------------------------------------
# Constraints: одно уникальное поле-идентификатор на тип узла
# ---------------------------------------------------------------------------
CONSTRAINTS: list[tuple[str, str]] = [
    # (constraint_name, cypher)
    (
        "candidate_id_unique",
        "CREATE CONSTRAINT candidate_id_unique IF NOT EXISTS "
        "FOR (n:Candidate) REQUIRE n.id IS UNIQUE",
    ),
    (
        "contact_id_unique",
        "CREATE CONSTRAINT contact_id_unique IF NOT EXISTS "
        "FOR (n:Contact) REQUIRE n.id IS UNIQUE",
    ),
    (
        "skill_name_unique",
        "CREATE CONSTRAINT skill_name_unique IF NOT EXISTS "
        "FOR (n:Skill) REQUIRE n.name IS UNIQUE",
    ),
    (
        "role_title_unique",
        "CREATE CONSTRAINT role_title_unique IF NOT EXISTS "
        "FOR (n:Role) REQUIRE n.title IS UNIQUE",
    ),
    (
        "company_name_unique",
        "CREATE CONSTRAINT company_name_unique IF NOT EXISTS "
        "FOR (n:Company) REQUIRE n.name IS UNIQUE",
    ),
    (
        "experience_id_unique",
        "CREATE CONSTRAINT experience_id_unique IF NOT EXISTS "
        "FOR (n:Experience) REQUIRE n.id IS UNIQUE",
    ),
    (
        "education_id_unique",
        "CREATE CONSTRAINT education_id_unique IF NOT EXISTS "
        "FOR (n:Education) REQUIRE n.id IS UNIQUE",
    ),
    (
        "vacancy_id_unique",
        "CREATE CONSTRAINT vacancy_id_unique IF NOT EXISTS "
        "FOR (n:Vacancy) REQUIRE n.id IS UNIQUE",
    ),
    (
        "status_id_unique",
        "CREATE CONSTRAINT status_id_unique IF NOT EXISTS "
        "FOR (n:Status) REQUIRE n.id IS UNIQUE",
    ),
    (
        "hrnote_id_unique",
        "CREATE CONSTRAINT hrnote_id_unique IF NOT EXISTS "
        "FOR (n:HRNote) REQUIRE n.id IS UNIQUE",
    ),
    (
        "document_id_unique",
        "CREATE CONSTRAINT document_id_unique IF NOT EXISTS "
        "FOR (n:Document) REQUIRE n.id IS UNIQUE",
    ),
    (
        "fact_id_unique",
        "CREATE CONSTRAINT fact_id_unique IF NOT EXISTS "
        "FOR (n:Fact) REQUIRE n.id IS UNIQUE",
    ),
]

# ---------------------------------------------------------------------------
# Indexes: поля, по которым часто ищем (не уникальные)
# ---------------------------------------------------------------------------
INDEXES: list[tuple[str, str]] = [
    # (index_name, cypher)
    (
        "candidate_full_name_idx",
        "CREATE INDEX candidate_full_name_idx IF NOT EXISTS "
        "FOR (n:Candidate) ON (n.full_name)",
    ),
    (
        "experience_is_current_idx",
        "CREATE INDEX experience_is_current_idx IF NOT EXISTS "
        "FOR (n:Experience) ON (n.is_current)",
    ),
    (
        "fact_is_current_idx",
        "CREATE INDEX fact_is_current_idx IF NOT EXISTS "
        "FOR (n:Fact) ON (n.is_current)",
    ),
    (
        "fact_predicate_idx",
        "CREATE INDEX fact_predicate_idx IF NOT EXISTS "
        "FOR (n:Fact) ON (n.predicate)",
    ),
]


async def main() -> None:
    settings = get_settings()
    db = GraphDB(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
    )

    try:
        await db.connect_with_retry()
        if not db.is_connected:
            logger.error("Neo4j unavailable — migration aborted")
            sys.exit(1)

        async with db.session() as session:
            for name, cypher in CONSTRAINTS:
                await session.run(cypher)
                logger.info("constraint applied: {}", name)

            for name, cypher in INDEXES:
                await session.run(cypher)
                logger.info("index applied: {}", name)

        logger.info(
            "Migration complete: {} constraints, {} indexes",
            len(CONSTRAINTS),
            len(INDEXES),
        )
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
