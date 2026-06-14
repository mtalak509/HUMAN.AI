from loguru import logger

from core.database.graph import GraphDB


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
    (
        "document_processing_status_idx",
        "CREATE INDEX document_processing_status_idx IF NOT EXISTS "
        "FOR (n:Document) ON (n.processing_status)",
    ),
]


class MigrationManager:
    def __init__(self, db: GraphDB) -> None:
        self.db = db

    async def apply_all(self) -> None:
        """Apply all constraints and indexes. Idempotent."""
        if not self.db.is_connected:
            logger.warning("Neo4j unavailable — skipping schema migration")
            return

        async with self.db.session() as session:
            for name, cypher in CONSTRAINTS:
                await session.run(cypher)
                logger.debug("constraint applied: {}", name)
            for name, cypher in INDEXES:
                await session.run(cypher)
                logger.debug("index applied: {}", name)

        logger.info(
            "Schema up to date: {} constraints, {} indexes",
            len(CONSTRAINTS),
            len(INDEXES),
        )
