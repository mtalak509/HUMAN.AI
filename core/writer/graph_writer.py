"""core.writer.graph_writer — GraphWriter async service.

Turns an ExtractedCandidate into a full candidate graph in Neo4j.

Responsibilities (plan 06-02):
  - Deterministic ID derivation (D-01): sha1 of fixed field strings
  - Skill union + strip-only dedup (D-04/D-05): top-level ∪ skills_mentioned
  - Fact provenance (D-02/D-03): Fact per unique skill + per experience
  - USED_SKILL edge (D-06): Experience→Skill for skills_mentioned
  - Single write transaction for atomicity (execute_write)
  - Graceful degradation (T-06-07): is_connected guard, no crash on Neo4j outage

Security (T-06-04): ONLY binds params to pre-audited cypher.py constants.
                    Never builds Cypher strings.
Security (T-06-05): Fact.model_version = candidate.model_version (caller-stamped).
                    confidence = None (D-02, never invented).
Security (T-06-06): EXTRACTED_FROM links to Document by id (provenance audit trail).
"""

import datetime as dt
import hashlib

from loguru import logger

from core.config import Settings, get_settings
from core.database.graph import GraphDB
from core.extractor.schema import ExtractedCandidate
from core.writer.cypher import (
    LINK_AS_ROLE,
    LINK_AT_COMPANY,
    LINK_EXTRACTED_FROM,
    LINK_HAS_CONTACT,
    LINK_HAS_EDUCATION,
    LINK_HAS_EXPERIENCE,
    LINK_HAS_FACT,
    LINK_HAS_SKILL,
    LINK_SUPPORTS_EXPERIENCE,
    LINK_SUPPORTS_SKILL,
    LINK_USED_SKILL,
    MERGE_CANDIDATE,
    MERGE_COMPANY,
    MERGE_CONTACT,
    MERGE_EDUCATION,
    MERGE_EXPERIENCE,
    MERGE_FACT,
    MERGE_ROLE,
    MERGE_SKILL,
)


class GraphWriter:
    """Async service that writes one ExtractedCandidate to the Neo4j graph.

    Constructor is dependency-injectable (mirrors PdfParser DI pattern):
      - db: GraphDB | None — None is safe (degraded mode, no crash)
      - settings: Settings | None — defaults to get_settings()

    Called from Celery in phase 7 (NOT FastAPI Depends).

    Usage:
        writer = GraphWriter(db=graph_db)
        await writer.write(candidate, document_id)
    """

    def __init__(
        self,
        db: GraphDB | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._db = db
        self._settings = settings or get_settings()

    # ------------------------------------------------------------------
    # Deterministic ID helpers (D-01)
    # ------------------------------------------------------------------

    @staticmethod
    def _experience_id(document_id: str, company: str, role: str, from_date: str) -> str:
        """sha1(document_id|company|role|from_date) — deterministic, 40-char hex."""
        return hashlib.sha1(
            f"{document_id}|{company}|{role}|{from_date}".encode()
        ).hexdigest()

    @staticmethod
    def _education_id(document_id: str, institution: str, from_date: str | None) -> str:
        """sha1(document_id|institution|from_date) — deterministic, 40-char hex."""
        return hashlib.sha1(
            f"{document_id}|{institution}|{from_date}".encode()
        ).hexdigest()

    @staticmethod
    def _contact_id(document_id: str, type_: str, value: str) -> str:
        """sha1(document_id|type|value) — deterministic, 40-char hex."""
        return hashlib.sha1(
            f"{document_id}|{type_}|{value}".encode()
        ).hexdigest()

    @staticmethod
    def _fact_id(document_id: str, predicate: str, value: str) -> str:
        """sha1(document_id|predicate|value) — deterministic, 40-char hex."""
        return hashlib.sha1(
            f"{document_id}|{predicate}|{value}".encode()
        ).hexdigest()

    # ------------------------------------------------------------------
    # Public write entry point
    # ------------------------------------------------------------------

    async def write(self, candidate: ExtractedCandidate, document_id: str) -> None:
        """Write the full candidate graph to Neo4j in a single transaction.

        Args:
            candidate: Validated ExtractedCandidate from the LLM extractor.
            document_id: SHA-256 hex of the source PDF (= candidate_id per D-01).

        Graceful degradation (T-06-07):
            If db is None or not connected, logs a warning and returns without
            crashing. The caller (Celery phase 7) is responsible for retry logic.
        """
        candidate_id = document_id  # D-01: 1 resume = 1 candidate

        if self._db is None or not self._db.is_connected:
            logger.warning(
                "graph_writer: Neo4j unavailable — candidate graph not persisted id={}",
                candidate_id,
            )
            return

        async with self._db.session() as session:
            await session.execute_write(self._write_tx, candidate, candidate_id)

        logger.info("graph_writer: candidate graph written id={}", candidate_id)

    # ------------------------------------------------------------------
    # Transaction function (all tx.run calls, one atomic write)
    # ------------------------------------------------------------------

    async def _write_tx(
        self,
        tx,  # neo4j.AsyncManagedTransaction
        candidate: ExtractedCandidate,
        candidate_id: str,
    ) -> None:
        """Run all MERGE/LINK statements inside a single managed write transaction.

        Statement ORDER mirrors scripts/seed.py:
        1. Candidate node
        2. Contacts (nodes + edges)
        3. Skills (nodes + edges) — full union D-04/D-05
        4. Experiences (nodes + company/role/edges + USED_SKILL)
        5. Education (nodes + edges)
        6. Fact provenance (one per unique skill + one per experience)
        """
        document_id = candidate_id  # same value; alias for clarity in Fact links

        # Timestamp stamped once per transaction (mirrors pdf.py line 175)
        now = dt.datetime.now(dt.UTC).isoformat()

        # Build skill union (D-04/D-05): .strip() + dedup, no lowercasing
        skills: set[str] = {s.strip() for s in candidate.skills}
        for exp in candidate.experiences:
            skills |= {s.strip() for s in exp.skills_mentioned}
        skills.discard("")  # remove empty strings if any

        # ------------------------------------------------------------------
        # 1. Candidate node
        # ------------------------------------------------------------------
        await tx.run(
            MERGE_CANDIDATE,
            id=candidate_id,
            full_name=candidate.full_name,
            status="active",
        )

        # ------------------------------------------------------------------
        # 2. Contacts
        # ------------------------------------------------------------------
        for contact in candidate.contacts:
            ct_id = self._contact_id(document_id, contact.type, contact.value)
            await tx.run(
                MERGE_CONTACT,
                id=ct_id,
                type=contact.type,
                value=contact.value,
            )
            await tx.run(
                LINK_HAS_CONTACT,
                c_id=candidate_id,
                ct_id=ct_id,
            )

        # ------------------------------------------------------------------
        # 3. Skills (full union)
        # ------------------------------------------------------------------
        for skill in skills:
            await tx.run(MERGE_SKILL, name=skill)
            await tx.run(LINK_HAS_SKILL, c_id=candidate_id, name=skill)

        # ------------------------------------------------------------------
        # 4. Experiences
        # ------------------------------------------------------------------
        for exp in candidate.experiences:
            exp_id = self._experience_id(
                document_id, exp.company, exp.role, exp.from_date
            )

            # Nodes
            await tx.run(MERGE_COMPANY, name=exp.company, industry=None)
            await tx.run(MERGE_ROLE, title=exp.role, seniority=None)
            await tx.run(
                MERGE_EXPERIENCE,
                id=exp_id,
                from_date=exp.from_date,
                to_date=exp.to_date,
                is_current=exp.is_current,
            )

            # Edges
            await tx.run(LINK_HAS_EXPERIENCE, c_id=candidate_id, e_id=exp_id)
            await tx.run(LINK_AT_COMPANY, e_id=exp_id, name=exp.company)
            await tx.run(LINK_AS_ROLE, e_id=exp_id, title=exp.role)

            # USED_SKILL edges (D-06): skills_mentioned in this role
            for s in exp.skills_mentioned:
                s = s.strip()
                if s:
                    await tx.run(LINK_USED_SKILL, e_id=exp_id, name=s)

        # ------------------------------------------------------------------
        # 5. Education
        # ------------------------------------------------------------------
        for edu in candidate.education:
            edu_id = self._education_id(document_id, edu.institution, edu.from_date)
            await tx.run(
                MERGE_EDUCATION,
                id=edu_id,
                institution=edu.institution,
                degree=edu.degree,
                field=edu.field,
                from_date=edu.from_date,
                to_date=edu.to_date,
            )
            await tx.run(LINK_HAS_EDUCATION, c_id=candidate_id, ed_id=edu_id)

        # ------------------------------------------------------------------
        # 6. Fact provenance (D-03/D-07)
        # ------------------------------------------------------------------

        # One Fact per UNIQUE skill (D-07): predicate="has_skill", SUPPORTS→Skill
        for skill in skills:
            f_id = self._fact_id(document_id, "has_skill", skill)
            await tx.run(
                MERGE_FACT,
                id=f_id,
                predicate="has_skill",
                value=skill,
                confidence=None,          # D-02: null, never a float
                model_version=candidate.model_version,
                is_current=True,
                extracted_at=now,
            )
            await tx.run(LINK_HAS_FACT, c_id=candidate_id, f_id=f_id)
            await tx.run(LINK_EXTRACTED_FROM, f_id=f_id, d_id=document_id)
            await tx.run(LINK_SUPPORTS_SKILL, f_id=f_id, name=skill)

        # One Fact per experience (D-03): predicate="worked_at", SUPPORTS→Experience
        for exp in candidate.experiences:
            exp_id = self._experience_id(
                document_id, exp.company, exp.role, exp.from_date
            )
            f_id = self._fact_id(document_id, "worked_at", exp.company)
            await tx.run(
                MERGE_FACT,
                id=f_id,
                predicate="worked_at",
                value=exp.company,
                confidence=None,          # D-02: null, never a float
                model_version=candidate.model_version,
                is_current=True,
                extracted_at=now,
            )
            await tx.run(LINK_HAS_FACT, c_id=candidate_id, f_id=f_id)
            await tx.run(LINK_EXTRACTED_FROM, f_id=f_id, d_id=document_id)
            await tx.run(LINK_SUPPORTS_EXPERIENCE, f_id=f_id, e_id=exp_id)
