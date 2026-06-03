"""
Идемпотентная загрузка тестового кандидата в Neo4j.

Запуск: python scripts/seed.py

Загружает единственного seed-кандидата — Алексей Соколов (id c-001).
Задействует все 12 типов узлов онтологии.
Повторный запуск не создаёт дублей (MERGE-ключи).
"""

import asyncio
import sys

from loguru import logger

from core.config import get_settings
from core.graph import GraphDB


async def _seed_candidate(session) -> None:  # noqa: ANN001
    """Создаёт / обновляет граф тестового кандидата через MERGE-запросы."""

    # ------------------------------------------------------------------
    # 1. Узлы
    # ------------------------------------------------------------------

    # Candidate
    await session.run(
        "MERGE (n:Candidate {id: $id}) "
        "ON CREATE SET n.full_name=$full_name, n.status=$status "
        "ON MATCH SET n.full_name=$full_name, n.status=$status",
        id="c-001",
        full_name="Алексей Соколов",
        status="active",
    )
    logger.info("node: Candidate c-001")

    # Contact
    await session.run(
        "MERGE (n:Contact {id: $id}) "
        "ON CREATE SET n.type=$type, n.value=$value "
        "ON MATCH SET n.type=$type, n.value=$value",
        id="ct-001",
        type="email",
        value="sokolov@example.com",
    )
    logger.info("node: Contact ct-001")

    # Skills (5 узлов, MERGE по name)
    for skill_name in ["Python", "FastAPI", "Neo4j", "machine learning", "PostgreSQL"]:
        await session.run(
            "MERGE (n:Skill {name: $name})",
            name=skill_name,
        )
    logger.info("nodes: Skill x5")

    # Companies (MERGE по name)
    await session.run(
        "MERGE (n:Company {name: $name}) "
        "ON CREATE SET n.industry=$industry "
        "ON MATCH SET n.industry=$industry",
        name="TechFlow Analytics",
        industry="technology",
    )
    await session.run(
        "MERGE (n:Company {name: $name}) "
        "ON CREATE SET n.industry=$industry "
        "ON MATCH SET n.industry=$industry",
        name="DataVision Lab",
        industry="data science",
    )
    logger.info("nodes: Company x2")

    # Roles (MERGE по title)
    await session.run(
        "MERGE (n:Role {title: $title}) "
        "ON CREATE SET n.seniority=$seniority "
        "ON MATCH SET n.seniority=$seniority",
        title="Senior Python Engineer",
        seniority="senior",
    )
    await session.run(
        "MERGE (n:Role {title: $title}) "
        "ON CREATE SET n.seniority=$seniority "
        "ON MATCH SET n.seniority=$seniority",
        title="Python Developer",
        seniority="middle",
    )
    logger.info("nodes: Role x2")

    # Experience 1 (текущая)
    await session.run(
        "MERGE (n:Experience {id: $id}) "
        "ON CREATE SET n.from_date=$from_date, n.is_current=$is_current "
        "ON MATCH SET n.from_date=$from_date, n.is_current=$is_current",
        id="exp-001",
        from_date="2021-01-01",
        is_current=True,
    )
    logger.info("node: Experience exp-001")

    # Experience 2 (прошлая)
    await session.run(
        "MERGE (n:Experience {id: $id}) "
        "ON CREATE SET n.from_date=$from_date, n.to_date=$to_date, n.is_current=$is_current "
        "ON MATCH SET n.from_date=$from_date, n.to_date=$to_date, n.is_current=$is_current",
        id="exp-002",
        from_date="2018-03-01",
        to_date="2020-12-31",
        is_current=False,
    )
    logger.info("node: Experience exp-002")

    # Education
    await session.run(
        "MERGE (n:Education {id: $id}) "
        "ON CREATE SET n.institution=$institution, n.degree=$degree, "
        "n.field=$field, n.from_date=$from_date, n.to_date=$to_date "
        "ON MATCH SET n.institution=$institution, n.degree=$degree, "
        "n.field=$field, n.from_date=$from_date, n.to_date=$to_date",
        id="edu-001",
        institution="МГУ им. Ломоносова",
        degree="Магистр",
        field="Прикладная математика",
        from_date="2012-09-01",
        to_date="2018-06-30",
    )
    logger.info("node: Education edu-001")

    # Vacancy
    await session.run(
        "MERGE (n:Vacancy {id: $id}) "
        "ON CREATE SET n.title=$title, n.status=$status "
        "ON MATCH SET n.title=$title, n.status=$status",
        id="v-001",
        title="ML Engineer",
        status="open",
    )
    logger.info("node: Vacancy v-001")

    # Status
    await session.run(
        "MERGE (n:Status {id: $id}) "
        "ON CREATE SET n.name=$name "
        "ON MATCH SET n.name=$name",
        id="st-001",
        name="in_progress",
    )
    logger.info("node: Status st-001")

    # HRNote
    await session.run(
        "MERGE (n:HRNote {id: $id}) "
        "ON CREATE SET n.author=$author, n.text=$text "
        "ON MATCH SET n.author=$author, n.text=$text",
        id="hn-001",
        author="Мария Иванова",
        text=(
            "Сильный кандидат. Хорошо знает Neo4j и ML. "
            "Рекомендую к следующему этапу."
        ),
    )
    logger.info("node: HRNote hn-001")

    # Document
    await session.run(
        "MERGE (n:Document {id: $id}) "
        "ON CREATE SET n.type=$type, n.file_uri=$file_uri "
        "ON MATCH SET n.type=$type, n.file_uri=$file_uri",
        id="doc-001",
        type="resume",
        file_uri="storage/documents/doc-001/resume.pdf",
    )
    logger.info("node: Document doc-001")

    # Fact 1 (provenance для Python skill)
    await session.run(
        "MERGE (n:Fact {id: $id}) "
        "ON CREATE SET n.predicate=$predicate, n.value=$value, "
        "n.confidence=$confidence, n.model_version=$model_version, n.is_current=$is_current "
        "ON MATCH SET n.predicate=$predicate, n.value=$value, "
        "n.confidence=$confidence, n.model_version=$model_version, n.is_current=$is_current",
        id="f-001",
        predicate="has_skill",
        value="Python",
        confidence=0.95,
        model_version="seed-v1",
        is_current=True,
    )
    logger.info("node: Fact f-001")

    # Fact 2 (provenance для TechFlow опыта)
    await session.run(
        "MERGE (n:Fact {id: $id}) "
        "ON CREATE SET n.predicate=$predicate, n.value=$value, "
        "n.confidence=$confidence, n.model_version=$model_version, n.is_current=$is_current "
        "ON MATCH SET n.predicate=$predicate, n.value=$value, "
        "n.confidence=$confidence, n.model_version=$model_version, n.is_current=$is_current",
        id="f-002",
        predicate="worked_at",
        value="TechFlow Analytics",
        confidence=1.0,
        model_version="seed-v1",
        is_current=True,
    )
    logger.info("node: Fact f-002")

    # ------------------------------------------------------------------
    # 2. Связи
    # ------------------------------------------------------------------

    # (Candidate)-[:HAS_CONTACT]->(Contact)
    await session.run(
        "MATCH (c:Candidate {id: $c_id}) MATCH (ct:Contact {id: $ct_id}) "
        "MERGE (c)-[:HAS_CONTACT]->(ct)",
        c_id="c-001",
        ct_id="ct-001",
    )

    # (Candidate)-[:HAS_SKILL]->(Skill) x5
    for skill_name in ["Python", "FastAPI", "Neo4j", "machine learning", "PostgreSQL"]:
        await session.run(
            "MATCH (c:Candidate {id: $c_id}) MATCH (s:Skill {name: $name}) "
            "MERGE (c)-[:HAS_SKILL]->(s)",
            c_id="c-001",
            name=skill_name,
        )

    # Experience exp-001: связи с кандидатом, компанией, ролью
    await session.run(
        "MATCH (c:Candidate {id: $c_id}) MATCH (e:Experience {id: $e_id}) "
        "MERGE (c)-[:HAS_EXPERIENCE]->(e)",
        c_id="c-001",
        e_id="exp-001",
    )
    await session.run(
        "MATCH (e:Experience {id: $e_id}) MATCH (co:Company {name: $name}) "
        "MERGE (e)-[:AT_COMPANY]->(co)",
        e_id="exp-001",
        name="TechFlow Analytics",
    )
    await session.run(
        "MATCH (e:Experience {id: $e_id}) MATCH (r:Role {title: $title}) "
        "MERGE (e)-[:AS_ROLE]->(r)",
        e_id="exp-001",
        title="Senior Python Engineer",
    )

    # Experience exp-002: связи с кандидатом, компанией, ролью
    await session.run(
        "MATCH (c:Candidate {id: $c_id}) MATCH (e:Experience {id: $e_id}) "
        "MERGE (c)-[:HAS_EXPERIENCE]->(e)",
        c_id="c-001",
        e_id="exp-002",
    )
    await session.run(
        "MATCH (e:Experience {id: $e_id}) MATCH (co:Company {name: $name}) "
        "MERGE (e)-[:AT_COMPANY]->(co)",
        e_id="exp-002",
        name="DataVision Lab",
    )
    await session.run(
        "MATCH (e:Experience {id: $e_id}) MATCH (r:Role {title: $title}) "
        "MERGE (e)-[:AS_ROLE]->(r)",
        e_id="exp-002",
        title="Python Developer",
    )

    # (Candidate)-[:HAS_EDUCATION]->(Education)
    await session.run(
        "MATCH (c:Candidate {id: $c_id}) MATCH (ed:Education {id: $ed_id}) "
        "MERGE (c)-[:HAS_EDUCATION]->(ed)",
        c_id="c-001",
        ed_id="edu-001",
    )

    # (Candidate)-[:APPLIED_TO]->(Vacancy)
    await session.run(
        "MATCH (c:Candidate {id: $c_id}) MATCH (v:Vacancy {id: $v_id}) "
        "MERGE (c)-[:APPLIED_TO]->(v)",
        c_id="c-001",
        v_id="v-001",
    )

    # (Candidate)-[:REACHED_STATUS]->(Status)-[:IN_VACANCY]->(Vacancy)
    await session.run(
        "MATCH (c:Candidate {id: $c_id}) MATCH (st:Status {id: $st_id}) "
        "MERGE (c)-[:REACHED_STATUS]->(st)",
        c_id="c-001",
        st_id="st-001",
    )
    await session.run(
        "MATCH (st:Status {id: $st_id}) MATCH (v:Vacancy {id: $v_id}) "
        "MERGE (st)-[:IN_VACANCY]->(v)",
        st_id="st-001",
        v_id="v-001",
    )

    # (HRNote)-[:ABOUT]->(Candidate)
    await session.run(
        "MATCH (hn:HRNote {id: $hn_id}) MATCH (c:Candidate {id: $c_id}) "
        "MERGE (hn)-[:ABOUT]->(c)",
        hn_id="hn-001",
        c_id="c-001",
    )

    # Fact f-001: HAS_FACT, EXTRACTED_FROM, SUPPORTS (Skill Python)
    await session.run(
        "MATCH (c:Candidate {id: $c_id}) MATCH (f:Fact {id: $f_id}) "
        "MERGE (c)-[:HAS_FACT]->(f)",
        c_id="c-001",
        f_id="f-001",
    )
    await session.run(
        "MATCH (f:Fact {id: $f_id}) MATCH (d:Document {id: $d_id}) "
        "MERGE (f)-[:EXTRACTED_FROM]->(d)",
        f_id="f-001",
        d_id="doc-001",
    )
    await session.run(
        "MATCH (f:Fact {id: $f_id}) MATCH (s:Skill {name: $name}) "
        "MERGE (f)-[:SUPPORTS]->(s)",
        f_id="f-001",
        name="Python",
    )

    # Fact f-002: HAS_FACT, EXTRACTED_FROM, SUPPORTS (Experience exp-001)
    await session.run(
        "MATCH (c:Candidate {id: $c_id}) MATCH (f:Fact {id: $f_id}) "
        "MERGE (c)-[:HAS_FACT]->(f)",
        c_id="c-001",
        f_id="f-002",
    )
    await session.run(
        "MATCH (f:Fact {id: $f_id}) MATCH (d:Document {id: $d_id}) "
        "MERGE (f)-[:EXTRACTED_FROM]->(d)",
        f_id="f-002",
        d_id="doc-001",
    )
    await session.run(
        "MATCH (f:Fact {id: $f_id}) MATCH (e:Experience {id: $e_id}) "
        "MERGE (f)-[:SUPPORTS]->(e)",
        f_id="f-002",
        e_id="exp-001",
    )

    logger.info("relationships: all wired")


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
            logger.error("Neo4j unavailable — seed aborted")
            sys.exit(1)
        async with db.session() as session:
            await _seed_candidate(session)
        logger.info("Seed complete: candidate c-001 loaded")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
