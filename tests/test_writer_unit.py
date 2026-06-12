"""Unit tests for core.writer.graph_writer.GraphWriter.

Tests use mocked Neo4j db — no network calls, no infra required.
All async tests use session-scoped loop (per CLAUDE.md asyncio fixture pattern).

Behaviour tested:
  1. ID helpers are deterministic: same inputs → same hash; different inputs → different hash.
  2. Skill union + dedup: top-level ∪ skills_mentioned, .strip() collapse, case preserved.
  3. Graceful degradation: db=None → no exception, no session entered.
     db.is_connected=False → session() never called.
  4. One has_skill Fact per UNIQUE skill (D-07): no duplicate fact ids even when a skill
     appears in both top-level skills and in a role's skills_mentioned.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.extractor.schema import Contact, Education, Experience, ExtractedCandidate
from core.writer.cypher import (
    LINK_SUPPORTS_EXPERIENCE,
    MERGE_EXPERIENCE,
    MERGE_FACT,
    MERGE_SKILL,
)
from core.writer.graph_writer import GraphWriter

pytestmark = pytest.mark.asyncio(loop_scope="session")

# ---------------------------------------------------------------------------
# Shared fixture — a small ExtractedCandidate with deliberate overlaps
# ---------------------------------------------------------------------------

def _make_candidate(
    doc_id: str = "docabc",
    top_skills: list[str] | None = None,
    exp_skills: list[str] | None = None,
) -> ExtractedCandidate:
    """Build a minimal ExtractedCandidate for testing."""
    if top_skills is None:
        top_skills = ["Python", "  Python  ", "FastAPI"]  # duplicate + whitespace
    if exp_skills is None:
        exp_skills = ["Python", "Neo4j"]  # "Python" overlaps with top-level

    return ExtractedCandidate(
        document_id=doc_id,
        model_version="test-model",
        full_name="Test User",
        contacts=[Contact(type="email", value="test@example.com")],
        experiences=[
            Experience(
                from_date="2020-01",
                to_date=None,
                company="Acme Corp",
                role="Engineer",
                description="Built things",
                skills_mentioned=exp_skills,
            )
        ],
        education=[
            Education(
                institution="MIT",
                degree="BSc",
                field="CS",
                from_date="2016",
                to_date="2020",
            )
        ],
        skills=top_skills,
    )


# ---------------------------------------------------------------------------
# Test 1: ID helpers are deterministic
# ---------------------------------------------------------------------------


def test_ids_deterministic() -> None:
    """All 4 ID helpers: same inputs → equal hash; different inputs → different hash."""
    doc = "docabc"

    # _experience_id
    a = GraphWriter._experience_id(doc, "Acme", "Engineer", "2020-01")
    b = GraphWriter._experience_id(doc, "Acme", "Engineer", "2020-01")
    assert a == b, "_experience_id must be deterministic"
    assert len(a) == 40, "_experience_id must be 40-char sha1 hex"
    c = GraphWriter._experience_id(doc, "Acme", "Engineer", "2021-01")  # different from_date
    assert a != c, "_experience_id must differ for different from_date"

    # _education_id
    a = GraphWriter._education_id(doc, "MIT", "2016")
    b = GraphWriter._education_id(doc, "MIT", "2016")
    assert a == b
    assert len(a) == 40
    c = GraphWriter._education_id(doc, "Stanford", "2016")
    assert a != c

    # _contact_id
    a = GraphWriter._contact_id(doc, "email", "x@example.com")
    b = GraphWriter._contact_id(doc, "email", "x@example.com")
    assert a == b
    assert len(a) == 40
    c = GraphWriter._contact_id(doc, "phone", "x@example.com")
    assert a != c

    # _fact_id
    a = GraphWriter._fact_id(doc, "has_skill", "Python")
    b = GraphWriter._fact_id(doc, "has_skill", "Python")
    assert a == b
    assert len(a) == 40
    c = GraphWriter._fact_id(doc, "has_skill", "FastAPI")
    assert a != c


# ---------------------------------------------------------------------------
# Test 2: Skill union + dedup (D-04/D-05)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skill_union_dedup() -> None:
    """Union of top-level skills + skills_mentioned: strip, dedup, case preserved.

    Drives the REAL GraphWriter via the capturing-tx mock and asserts on the
    `name=` arguments actually passed to MERGE_SKILL — not a re-implementation of
    the union logic (WR-04). If the writer's union logic regresses, this fails.
    """
    cand = _make_candidate(
        top_skills=["Python", "  Python  ", "FastAPI"],
        exp_skills=["Python", "Neo4j"],
    )

    mock_db, mock_tx = _build_mock_db_with_capturing_tx()
    await GraphWriter(db=mock_db).write(cand, "docabc")

    # Collect the skill names the writer actually MERGEd
    merged_skill_names = [
        kwargs["name"]
        for (args, kwargs) in mock_tx.run.call_args_list
        if (args[0] if args else kwargs.get("query", "")) == MERGE_SKILL
    ]

    assert set(merged_skill_names) == {"Python", "FastAPI", "Neo4j"}, (
        f"Expected {{'Python', 'FastAPI', 'Neo4j'}}, got {set(merged_skill_names)}"
    )
    # No duplicate MERGE_SKILL calls ("  Python  " collapses to "Python")
    assert len(merged_skill_names) == len(set(merged_skill_names)), (
        f"Duplicate MERGE_SKILL calls: {merged_skill_names}"
    )
    # Case preserved ("Python" not "python"); no empty strings
    assert "Python" in merged_skill_names
    assert "" not in merged_skill_names


# ---------------------------------------------------------------------------
# Test 3: Graceful degradation (T-06-07)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_degrades_when_db_down() -> None:
    """write() with db=None returns None without raising any exception."""
    cand = _make_candidate()
    result = await GraphWriter(db=None).write(cand, "docabc")
    assert result is None  # write() returns None on degradation


@pytest.mark.asyncio
async def test_write_session_never_entered_when_not_connected() -> None:
    """write() with db.is_connected=False never calls db.session()."""
    cand = _make_candidate()

    mock_db = MagicMock()
    mock_db.is_connected = False

    await GraphWriter(db=mock_db).write(cand, "docabc")

    mock_db.session.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4: One Fact per unique skill — D-07
# ---------------------------------------------------------------------------

def _build_mock_db_with_capturing_tx():
    """Build a mock GraphDB whose execute_write runs the real _write_tx against a mock tx.

    Returns (mock_db, mock_tx) so callers can inspect tx.run call_args_list.
    """
    mock_tx = MagicMock()
    mock_tx.run = AsyncMock()

    # execute_write(fn, *args) — call fn(mock_tx, *args) directly
    async def fake_execute_write(fn, *args, **kwargs):
        await fn(mock_tx, *args, **kwargs)

    mock_session = MagicMock()
    mock_session.execute_write = fake_execute_write

    @asynccontextmanager
    async def fake_session_cm():
        yield mock_session

    mock_db = MagicMock()
    mock_db.is_connected = True
    mock_db.session = fake_session_cm

    return mock_db, mock_tx


@pytest.mark.asyncio
async def test_one_fact_per_unique_skill() -> None:
    """D-07: exactly one has_skill Fact id per unique skill, zero duplicates."""
    cand = _make_candidate(
        top_skills=["Python", "  Python  ", "FastAPI"],
        exp_skills=["Python", "Neo4j"],
    )
    expected_unique_skills = {"Python", "FastAPI", "Neo4j"}

    mock_db, mock_tx = _build_mock_db_with_capturing_tx()
    writer = GraphWriter(db=mock_db)
    await writer.write(cand, "docabc")

    # Filter tx.run calls for MERGE_FACT with predicate=="has_skill"
    has_skill_fact_ids = []
    for call in mock_tx.run.call_args_list:
        args, kwargs = call
        # First positional arg is the statement string
        stmt = args[0] if args else kwargs.get("query", "")
        if stmt == MERGE_FACT:
            if kwargs.get("predicate") == "has_skill":
                has_skill_fact_ids.append(kwargs["id"])

    # No duplicates
    assert len(has_skill_fact_ids) == len(set(has_skill_fact_ids)), (
        f"Duplicate has_skill Fact ids found: {has_skill_fact_ids}"
    )
    # Count matches unique skill count
    assert len(has_skill_fact_ids) == len(expected_unique_skills), (
        f"Expected {len(expected_unique_skills)} has_skill Facts, got {len(has_skill_fact_ids)}"
    )


# ---------------------------------------------------------------------------
# Test 5: worked_at Fact does NOT collide for two roles at the same company (WR-01)
# ---------------------------------------------------------------------------


def _candidate_two_roles_same_company(doc_id: str = "docabc") -> ExtractedCandidate:
    """Two experiences at the SAME company, different role + from_date (a promotion)."""
    return ExtractedCandidate(
        document_id=doc_id,
        model_version="test-model",
        full_name="Test User",
        experiences=[
            Experience(from_date="2018-01", to_date="2021-01", company="Acme Corp",
                       role="Junior Engineer", skills_mentioned=[]),
            Experience(from_date="2021-02", to_date=None, company="Acme Corp",
                       role="Senior Engineer", skills_mentioned=[]),
        ],
        skills=[],
    )


@pytest.mark.asyncio
async def test_worked_at_fact_no_collision_same_company() -> None:
    """WR-01: two experiences at one company → two distinct worked_at Facts, each
    supporting its own Experience node (no id collision, no overwritten provenance)."""
    cand = _candidate_two_roles_same_company()

    mock_db, mock_tx = _build_mock_db_with_capturing_tx()
    await GraphWriter(db=mock_db).write(cand, "docabc")

    worked_at_fact_ids = []
    supports_exp_e_ids = []
    for call in mock_tx.run.call_args_list:
        args, kwargs = call
        stmt = args[0] if args else kwargs.get("query", "")
        if stmt == MERGE_FACT and kwargs.get("predicate") == "worked_at":
            worked_at_fact_ids.append(kwargs["id"])
        if stmt == LINK_SUPPORTS_EXPERIENCE:
            supports_exp_e_ids.append(kwargs["e_id"])

    # Two experiences → two distinct worked_at Fact ids (the bug produced one)
    assert len(worked_at_fact_ids) == 2, worked_at_fact_ids
    assert len(set(worked_at_fact_ids)) == 2, (
        f"worked_at Fact ids collided: {worked_at_fact_ids}"
    )
    # Each Fact supports a distinct Experience
    assert len(set(supports_exp_e_ids)) == 2, supports_exp_e_ids


# ---------------------------------------------------------------------------
# Test 6: experience with blank company/role is skipped (WR-02)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blank_company_experience_skipped() -> None:
    """WR-02: an experience whose company is blank after strip creates no
    Experience node and no worked_at Fact — no garbage shared nodes keyed on ''."""
    cand = ExtractedCandidate(
        document_id="docabc",
        model_version="test-model",
        full_name="Test User",
        experiences=[
            Experience(from_date="2020-01", to_date=None, company="   ",
                       role="Engineer", skills_mentioned=[]),
            Experience(from_date="2021-01", to_date=None, company="Acme Corp",
                       role="Engineer", skills_mentioned=[]),
        ],
        skills=[],
    )

    mock_db, mock_tx = _build_mock_db_with_capturing_tx()
    await GraphWriter(db=mock_db).write(cand, "docabc")

    merge_exp_calls = 0
    worked_at_facts = 0
    for call in mock_tx.run.call_args_list:
        args, kwargs = call
        stmt = args[0] if args else kwargs.get("query", "")
        if stmt == MERGE_EXPERIENCE:
            merge_exp_calls += 1
        if stmt == MERGE_FACT and kwargs.get("predicate") == "worked_at":
            worked_at_facts += 1

    # Only the valid experience is written
    assert merge_exp_calls == 1, f"Expected 1 Experience node, got {merge_exp_calls}"
    assert worked_at_facts == 1, f"Expected 1 worked_at Fact, got {worked_at_facts}"
