"""Integration tests for core.writer.graph_writer.GraphWriter.

Tests require a running Neo4j instance.  When Neo4j is unavailable
(graph_db.is_connected=False), every test skips cleanly.

Implemented in plan 06-02 (Wave 2 — GraphWriter service).

Covers:
  WRITE-01/02/03: candidate nodes + Fact provenance persisted in Neo4j
  WRITE-04: second write of the same document adds zero nodes (idempotency)
  Success criterion #5: candidate findable via find_candidates_by_skill/company
  D-06: USED_SKILL edge present for skills_mentioned
  T-06-06: Fact→EXTRACTED_FROM→Document triple reachable
"""

import pytest

from core.database.graph import GraphDB
from core.extractor.schema import Contact, Education, Experience, ExtractedCandidate
from core.writer.graph_writer import GraphWriter
from neo4j import AsyncDriver
from scripts.queries import find_candidates_by_company, find_candidates_by_skill

pytestmark = pytest.mark.asyncio(loop_scope="session")

# ---------------------------------------------------------------------------
# Fixed test document/candidate — same across reruns for idempotent CI
# ---------------------------------------------------------------------------

_DOC_ID = "test-doc-write-06"
_SKILL = "Python"
_COMPANY = "TechFlow Analytics"

_CANDIDATE = ExtractedCandidate(
    document_id=_DOC_ID,
    model_version="test-model-v1",
    full_name="Integration Test User",
    contacts=[Contact(type="email", value="integration@example.com")],
    experiences=[
        Experience(
            from_date="2021-01",
            to_date=None,
            company=_COMPANY,
            role="Backend Engineer",
            description="Worked on graph systems",
            skills_mentioned=[_SKILL],
        )
    ],
    education=[
        Education(
            institution="Test University",
            degree="BSc",
            field="Computer Science",
            from_date="2017",
            to_date="2021",
        )
    ],
    skills=[_SKILL, "FastAPI"],
)


# ---------------------------------------------------------------------------
# Setup helper — ensure Document stub exists (parser normally creates it;
# here we MERGE a minimal node so EXTRACTED_FROM links resolve)
# ---------------------------------------------------------------------------

async def _ensure_document_stub(graph_db: GraphDB) -> None:
    """MERGE a minimal Document node so EXTRACTED_FROM can link to it."""
    async with graph_db.session() as session:
        await session.run(
            "MERGE (d:Document {id: $id}) SET d.type = $type",
            id=_DOC_ID,
            type="resume",
        )


# ---------------------------------------------------------------------------
# Test 1: Candidate findable by skill + company (success criterion #5)
# ---------------------------------------------------------------------------


async def test_candidate_findable_by_skill_and_company(
    graph_db: GraphDB, neo4j_driver: AsyncDriver
) -> None:
    """After write(), candidate is findable via find_candidates_by_skill/company."""
    if not graph_db.is_connected:
        pytest.skip("Neo4j unavailable")

    await _ensure_document_stub(graph_db)
    await GraphWriter(db=graph_db).write(_CANDIDATE, _DOC_ID)

    # Success criterion #5 — queries.py must find the candidate
    by_skill = await find_candidates_by_skill(neo4j_driver, _SKILL)
    by_company = await find_candidates_by_company(neo4j_driver, _COMPANY)

    skill_ids = [r["id"] for r in by_skill]
    company_ids = [r["id"] for r in by_company]

    assert _DOC_ID in skill_ids, (
        f"Candidate {_DOC_ID!r} not found by skill {_SKILL!r}. Results: {skill_ids}"
    )
    assert _DOC_ID in company_ids, (
        f"Candidate {_DOC_ID!r} not found by company {_COMPANY!r}. Results: {company_ids}"
    )


# ---------------------------------------------------------------------------
# Test 2: Fact provenance triple reachable (T-06-06)
# ---------------------------------------------------------------------------


async def test_fact_provenance_reachable(graph_db: GraphDB) -> None:
    """Fact nodes are linked: Candidate-[:HAS_FACT]->Fact-[:EXTRACTED_FROM]->Document."""
    if not graph_db.is_connected:
        pytest.skip("Neo4j unavailable")

    await _ensure_document_stub(graph_db)
    await GraphWriter(db=graph_db).write(_CANDIDATE, _DOC_ID)

    async with graph_db.session() as session:
        # HAS_FACT → EXTRACTED_FROM triple
        r = await session.run(
            "MATCH (c:Candidate {id:$id})-[:HAS_FACT]->(f:Fact)"
            "-[:EXTRACTED_FROM]->(d:Document) "
            "RETURN count(f) AS c",
            id=_DOC_ID,
        )
        record = await r.single()
        assert record is not None
        assert record["c"] >= 1, (
            f"Expected at least 1 Fact with EXTRACTED_FROM provenance, got {record['c']}"
        )

        # SUPPORTS → Skill or Experience
        r2 = await session.run(
            "MATCH (f:Fact)-[:SUPPORTS]->(x) "
            "WHERE (x:Skill OR x:Experience) "
            "AND EXISTS { MATCH (:Candidate {id:$id})-[:HAS_FACT]->(f) } "
            "RETURN count(f) AS c",
            id=_DOC_ID,
        )
        record2 = await r2.single()
        assert record2 is not None
        assert record2["c"] >= 1, (
            f"Expected at least 1 SUPPORTS edge from Fact, got {record2['c']}"
        )


# ---------------------------------------------------------------------------
# Test 3: USED_SKILL edge exists (D-06)
# ---------------------------------------------------------------------------


async def test_used_skill_edge_exists(graph_db: GraphDB) -> None:
    """USED_SKILL edge exists from an Experience to Skill 'Python' (D-06)."""
    if not graph_db.is_connected:
        pytest.skip("Neo4j unavailable")

    await _ensure_document_stub(graph_db)
    await GraphWriter(db=graph_db).write(_CANDIDATE, _DOC_ID)

    async with graph_db.session() as session:
        r = await session.run(
            "MATCH (e:Experience)-[:USED_SKILL]->(s:Skill {name: $name}) "
            "RETURN count(*) AS c",
            name=_SKILL,
        )
        record = await r.single()
        assert record is not None
        assert record["c"] >= 1, (
            f"Expected USED_SKILL edge to Skill '{_SKILL}', found {record['c']}"
        )


# ---------------------------------------------------------------------------
# Test 4: Idempotency — WRITE-04
# ---------------------------------------------------------------------------


async def test_write_idempotent(graph_db: GraphDB) -> None:
    """WRITE-04: calling write() twice produces the same node counts as once.

    Asserts:
    - Exactly 1 Candidate node for this document_id
    - has_skill Fact count identical after 1st and 2nd write
    - Experience count identical after 1st and 2nd write
    """
    if not graph_db.is_connected:
        pytest.skip("Neo4j unavailable")

    await _ensure_document_stub(graph_db)
    writer = GraphWriter(db=graph_db)

    # First write
    await writer.write(_CANDIDATE, _DOC_ID)

    async def _counts(session) -> dict:  # noqa: ANN001
        r_candidate = await session.run(
            "MATCH (c:Candidate {id: $id}) RETURN count(c) AS c", id=_DOC_ID
        )
        rec_c = await r_candidate.single()

        r_facts = await session.run(
            "MATCH (c:Candidate {id: $id})-[:HAS_FACT]->(f:Fact {predicate: 'has_skill'}) "
            "RETURN count(f) AS c",
            id=_DOC_ID,
        )
        rec_f = await r_facts.single()

        r_exp = await session.run(
            "MATCH (c:Candidate {id: $id})-[:HAS_EXPERIENCE]->(e:Experience) "
            "RETURN count(e) AS c",
            id=_DOC_ID,
        )
        rec_e = await r_exp.single()

        return {
            "candidates": rec_c["c"] if rec_c else 0,
            "has_skill_facts": rec_f["c"] if rec_f else 0,
            "experiences": rec_e["c"] if rec_e else 0,
        }

    async with graph_db.session() as session:
        counts_after_first = await _counts(session)

    # Candidate must exist (count == 1)
    assert counts_after_first["candidates"] == 1, (
        f"Expected 1 Candidate node, got {counts_after_first['candidates']}"
    )

    # Second write — must be idempotent
    await writer.write(_CANDIDATE, _DOC_ID)

    async with graph_db.session() as session:
        counts_after_second = await _counts(session)

    # All counts unchanged
    assert counts_after_second["candidates"] == counts_after_first["candidates"], (
        f"Candidate count changed after 2nd write: "
        f"{counts_after_first['candidates']} → {counts_after_second['candidates']}"
    )
    assert counts_after_second["has_skill_facts"] == counts_after_first["has_skill_facts"], (
        f"has_skill Fact count changed after 2nd write: "
        f"{counts_after_first['has_skill_facts']} → {counts_after_second['has_skill_facts']}"
    )
    assert counts_after_second["experiences"] == counts_after_first["experiences"], (
        f"Experience count changed after 2nd write: "
        f"{counts_after_first['experiences']} → {counts_after_second['experiences']}"
    )
