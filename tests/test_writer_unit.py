"""Unit tests for core.writer.graph_writer.GraphWriter.

Tests use mocked Neo4j db — no network calls, no infra required.
All async tests use session-scoped loop (per CLAUDE.md asyncio fixture pattern).

Behaviour tested (graph refactor 2026-06-21):
  1. ID helpers are deterministic: same inputs → same hash; different inputs → different hash.
  2. Skill union + dedup: top-level ∪ skills_mentioned, .strip() collapse, case preserved.
  3. Graceful degradation: db=None → no exception, no session entered.
     db.is_connected=False → session() never called.
  4. Two experiences at the same company get DISTINCT Experience nodes (WR-01).
  5. Blank-company experience is skipped (WR-02).
  6. Provenance edge SOURCED_FROM is written once, carrying model_version + extracted_at.
  7. Institution is a shared node linked via AT_INSTITUTION.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.extractor.schema import Contact, Education, Experience, ExtractedCandidate
from core.writer.cypher import (
    LINK_AT_INSTITUTION,
    LINK_HAS_EXPERIENCE,
    LINK_SOURCED_FROM,
    MERGE_EDUCATION,
    MERGE_EXPERIENCE,
    MERGE_INSTITUTION,
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


def _calls_for(mock_tx, statement: str) -> list[dict]:
    """All kwargs dicts for tx.run calls whose statement == `statement`."""
    out = []
    for args, kwargs in mock_tx.run.call_args_list:
        stmt = args[0] if args else kwargs.get("query", "")
        if stmt == statement:
            out.append(kwargs)
    return out


# ---------------------------------------------------------------------------
# Test 1: ID helpers are deterministic
# ---------------------------------------------------------------------------


def test_ids_deterministic() -> None:
    """ID helpers: same inputs → equal hash; different inputs → different hash."""
    doc = "docabc"

    # _experience_id
    a = GraphWriter._experience_id(doc, "Acme", "Engineer", "2020-01")
    b = GraphWriter._experience_id(doc, "Acme", "Engineer", "2020-01")
    assert a == b, "_experience_id must be deterministic"
    assert len(a) == 40, "_experience_id must be 40-char sha1 hex"
    c = GraphWriter._experience_id(doc, "Acme", "Engineer", "2021-01")  # different from_date
    assert a != c, "_experience_id must differ for different from_date"

    # _education_id
    a = GraphWriter._education_id(doc, "MIT", "BSc", "CS", "2016", "2020")
    b = GraphWriter._education_id(doc, "MIT", "BSc", "CS", "2016", "2020")
    assert a == b
    assert len(a) == 40
    c = GraphWriter._education_id(doc, "Stanford", "BSc", "CS", "2016", "2020")
    assert a != c
    # Same institution + from_date but different degree → distinct id (the
    # multiple-degrees-from-one-university collision the old key suffered).
    d = GraphWriter._education_id(doc, "MIT", "MSc", "CS", None, "2022")
    e = GraphWriter._education_id(doc, "MIT", "BSc", "CS", None, "2020")
    assert d != e, "different degree/to_date must yield distinct education ids"

    # _contact_id
    a = GraphWriter._contact_id(doc, "email", "x@example.com")
    b = GraphWriter._contact_id(doc, "email", "x@example.com")
    assert a == b
    assert len(a) == 40
    c = GraphWriter._contact_id(doc, "phone", "x@example.com")
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

    merged_skill_names = [kw["name"] for kw in _calls_for(mock_tx, MERGE_SKILL)]

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
# Test 4: two roles at the same company → distinct Experience nodes (WR-01)
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
async def test_two_roles_same_company_distinct_experiences() -> None:
    """WR-01: two experiences at one company → two distinct Experience nodes,
    each linked to the candidate (no id collision on company name alone)."""
    cand = _candidate_two_roles_same_company()

    mock_db, mock_tx = _build_mock_db_with_capturing_tx()
    await GraphWriter(db=mock_db).write(cand, "docabc")

    exp_ids = [kw["id"] for kw in _calls_for(mock_tx, MERGE_EXPERIENCE)]
    has_exp_ids = [kw["e_id"] for kw in _calls_for(mock_tx, LINK_HAS_EXPERIENCE)]

    assert len(exp_ids) == 2, exp_ids
    assert len(set(exp_ids)) == 2, f"Experience ids collided: {exp_ids}"
    assert set(has_exp_ids) == set(exp_ids), "each Experience linked to candidate"
    # role is stored on the node now (no shared Role node)
    roles = {kw["role"] for kw in _calls_for(mock_tx, MERGE_EXPERIENCE)}
    assert roles == {"Junior Engineer", "Senior Engineer"}, roles


# ---------------------------------------------------------------------------
# Test 5: experience with blank company is skipped (WR-02)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blank_company_experience_skipped() -> None:
    """WR-02: an experience whose company is blank after strip creates no
    Experience node — no garbage shared nodes keyed on ''."""
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

    assert len(_calls_for(mock_tx, MERGE_EXPERIENCE)) == 1, "only the valid experience"


# ---------------------------------------------------------------------------
# Test 6: provenance edge SOURCED_FROM (replaces the Fact layer)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sourced_from_edge_written_once_with_provenance() -> None:
    """Exactly one SOURCED_FROM edge, stamped with model_version + extracted_at."""
    cand = _make_candidate(doc_id="docabc")

    mock_db, mock_tx = _build_mock_db_with_capturing_tx()
    await GraphWriter(db=mock_db).write(cand, "docabc")

    calls = _calls_for(mock_tx, LINK_SOURCED_FROM)
    assert len(calls) == 1, f"expected exactly one SOURCED_FROM edge, got {len(calls)}"
    kw = calls[0]
    assert kw["c_id"] == "docabc"
    assert kw["d_id"] == "docabc"
    assert kw["model_version"] == "test-model"  # caller-stamped, not the LLM
    assert kw["extracted_at"], "extracted_at must be set"


# ---------------------------------------------------------------------------
# Test 7: Institution is a shared node linked via AT_INSTITUTION
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_institution_node_and_edge() -> None:
    """Education links to a shared Institution node (AT_INSTITUTION)."""
    cand = _make_candidate(doc_id="docabc")  # education institution = "MIT"

    mock_db, mock_tx = _build_mock_db_with_capturing_tx()
    await GraphWriter(db=mock_db).write(cand, "docabc")

    inst_names = [kw["name"] for kw in _calls_for(mock_tx, MERGE_INSTITUTION)]
    assert inst_names == ["MIT"], inst_names
    assert len(_calls_for(mock_tx, LINK_AT_INSTITUTION)) == 1


@pytest.mark.asyncio
async def test_multiple_degrees_same_institution_distinct_educations() -> None:
    """WR-01 (Education): three degrees from one university with from_date=None
    must produce three distinct Education nodes — not collapse onto one MERGE id.

    Regression for the Talakin resume: bachelor's + master's + a refresher course
    all at МИРЭА, all with from_date=None. The old key (institution + from_date)
    hashed identically for all three, so only the last survived in the graph.
    """
    uni = "МИРЭА — Российский технологический университет, Москва"
    cand = ExtractedCandidate(
        document_id="docabc",
        model_version="test-model",
        full_name="Test User",
        education=[
            Education(institution=uni, degree="Магистр", field="Управление",
                      from_date=None, to_date="2022"),
            Education(institution=uni, degree="Бакалавр", field="Инноватика",
                      from_date=None, to_date="2020"),
            Education(institution=uni, degree="Повышение квалификации",
                      field="Менеджмент в ИТ", from_date=None, to_date="2022"),
        ],
        skills=[],
    )

    mock_db, mock_tx = _build_mock_db_with_capturing_tx()
    await GraphWriter(db=mock_db).write(cand, "docabc")

    edu_calls = _calls_for(mock_tx, MERGE_EDUCATION)
    edu_ids = [kw["id"] for kw in edu_calls]
    degrees = [kw["degree"] for kw in edu_calls]

    assert len(edu_ids) == 3, f"expected 3 Education MERGEs, got {len(edu_ids)}"
    assert len(set(edu_ids)) == 3, f"Education ids collided: {edu_ids}"
    assert set(degrees) == {"Магистр", "Бакалавр", "Повышение квалификации"}


@pytest.mark.asyncio
async def test_blank_institution_skipped() -> None:
    """An education entry with a blank institution creates no Institution link."""
    cand = ExtractedCandidate(
        document_id="docabc",
        model_version="test-model",
        full_name="Test User",
        education=[Education(institution="   ", degree="BSc", field="CS")],
        skills=[],
    )

    mock_db, mock_tx = _build_mock_db_with_capturing_tx()
    await GraphWriter(db=mock_db).write(cand, "docabc")

    assert len(_calls_for(mock_tx, MERGE_INSTITUTION)) == 0
    assert len(_calls_for(mock_tx, LINK_AT_INSTITUTION)) == 0
