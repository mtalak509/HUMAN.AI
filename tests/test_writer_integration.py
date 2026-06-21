"""Integration tests for core.writer.graph_writer.GraphWriter.

Tests require a running Neo4j instance.  When Neo4j is unavailable
(graph_db.is_connected=False), every test skips cleanly.

Implemented in plan 06-02 (Wave 2 — GraphWriter service).

Covers (graph refactor 2026-06-21):
  WRITE-01/02/03: candidate nodes + provenance persisted in Neo4j
  WRITE-04: second write of the same document adds zero nodes (idempotency)
  Success criterion #5: candidate findable via find_candidates_by_skill/company
  D-06: USED_SKILL edge present for skills_mentioned
  T-06-06: Candidate-[:SOURCED_FROM]->Document provenance edge reachable
  Institution: Education-[:AT_INSTITUTION]->Institution traversal
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
_INSTITUTION = "Test University"

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
# here we MERGE a minimal node so SOURCED_FROM links resolve)
# ---------------------------------------------------------------------------

async def _ensure_document_stub(graph_db: GraphDB) -> None:
    """MERGE a minimal Document node so SOURCED_FROM can link to it."""
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
# Test 2: Provenance edge + Institution traversal (T-06-06)
# ---------------------------------------------------------------------------


async def test_sourced_from_and_institution_reachable(graph_db: GraphDB) -> None:
    """Candidate-[:SOURCED_FROM]->Document carries provenance; Education-[:AT_INSTITUTION]
    ->Institution is traversable."""
    if not graph_db.is_connected:
        pytest.skip("Neo4j unavailable")

    await _ensure_document_stub(graph_db)
    await GraphWriter(db=graph_db).write(_CANDIDATE, _DOC_ID)

    async with graph_db.session() as session:
        # Provenance edge with model_version stamped on it
        r = await session.run(
            "MATCH (c:Candidate {id:$id})-[r:SOURCED_FROM]->(d:Document {id:$id}) "
            "RETURN r.model_version AS mv, r.extracted_at AS ts",
            id=_DOC_ID,
        )
        record = await r.single()
        assert record is not None, "SOURCED_FROM edge not found"
        assert record["mv"] == "test-model-v1", record["mv"]
        assert record["ts"], "extracted_at must be set on the edge"

        # Institution traversal: find candidate via their school
        r2 = await session.run(
            "MATCH (c:Candidate {id:$id})-[:HAS_EDUCATION]->(:Education)"
            "-[:AT_INSTITUTION]->(i:Institution {name:$name}) "
            "RETURN count(i) AS c",
            id=_DOC_ID,
            name=_INSTITUTION,
        )
        record2 = await r2.single()
        assert record2 is not None
        assert record2["c"] >= 1, (
            f"Expected Education→Institution edge to {_INSTITUTION!r}, got {record2['c']}"
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
    - Experience count identical after 1st and 2nd write
    - Exactly 1 SOURCED_FROM provenance edge after both writes (MERGE, not CREATE)
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

        r_exp = await session.run(
            "MATCH (c:Candidate {id: $id})-[:HAS_EXPERIENCE]->(e:Experience) "
            "RETURN count(e) AS c",
            id=_DOC_ID,
        )
        rec_e = await r_exp.single()

        r_src = await session.run(
            "MATCH (c:Candidate {id: $id})-[r:SOURCED_FROM]->(:Document) "
            "RETURN count(r) AS c",
            id=_DOC_ID,
        )
        rec_s = await r_src.single()

        return {
            "candidates": rec_c["c"] if rec_c else 0,
            "experiences": rec_e["c"] if rec_e else 0,
            "sourced_from": rec_s["c"] if rec_s else 0,
        }

    async with graph_db.session() as session:
        counts_after_first = await _counts(session)

    # Candidate must exist (count == 1)
    assert counts_after_first["candidates"] == 1, (
        f"Expected 1 Candidate node, got {counts_after_first['candidates']}"
    )
    assert counts_after_first["sourced_from"] == 1, (
        f"Expected 1 SOURCED_FROM edge, got {counts_after_first['sourced_from']}"
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
    assert counts_after_second["experiences"] == counts_after_first["experiences"], (
        f"Experience count changed after 2nd write: "
        f"{counts_after_first['experiences']} → {counts_after_second['experiences']}"
    )
    assert counts_after_second["sourced_from"] == counts_after_first["sourced_from"], (
        f"SOURCED_FROM edge count changed after 2nd write: "
        f"{counts_after_first['sourced_from']} → {counts_after_second['sourced_from']}"
    )
