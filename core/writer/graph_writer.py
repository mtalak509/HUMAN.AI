"""core.writer.graph_writer — GraphWriter async service.

Turns an ExtractedCandidate into a full candidate graph in Neo4j.

Responsibilities (plan 06-02; graph refactor 2026-06-21):
  - Deterministic ID derivation (D-01): sha1 of fixed field strings
  - Skill union + strip-only dedup (D-04/D-05): top-level ∪ skills_mentioned
  - USED_SKILL edge (D-06): Experience→Skill for skills_mentioned
  - Institution as a shared node (AT_INSTITUTION), mirroring Company
  - Provenance via Candidate-[:SOURCED_FROM]->Document (model_version +
    extracted_at on the edge) — the reified Fact layer was removed (overhead in
    the 1:1 world; returns with entity resolution in v1.2)
  - Single write transaction for atomicity (execute_write)
  - Graceful degradation (T-06-07): is_connected guard, no crash on Neo4j outage

Security (T-06-04): ONLY binds params to pre-audited cypher.py constants.
                    Never builds Cypher strings.
Security (T-06-05): SOURCED_FROM.model_version = candidate.model_version
                    (caller-stamped, never the LLM).
Security (T-06-06): SOURCED_FROM links Candidate to Document by id (audit trail).
"""

import datetime as dt
import hashlib

from loguru import logger

from core.config import Settings, get_settings
from core.database.graph import GraphDB
from core.extractor.schema import ExtractedCandidate
from core.writer.cypher import (
    LINK_AT_COMPANY,
    LINK_AT_INSTITUTION,
    LINK_HAS_CONTACT,
    LINK_HAS_EDUCATION,
    LINK_HAS_EXPERIENCE,
    LINK_HAS_SKILL,
    LINK_SOURCED_FROM,
    LINK_USED_SKILL,
    MERGE_CANDIDATE,
    MERGE_COMPANY,
    MERGE_CONTACT,
    MERGE_EDUCATION,
    MERGE_EXPERIENCE,
    MERGE_INSTITUTION,
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
    def _education_id(
        document_id: str,
        institution: str,
        degree: str,
        field: str,
        from_date: str | None,
        to_date: str | None,
    ) -> str:
        """sha1(document_id|institution|degree|field|from_date|to_date) — 40-char hex.

        degree + field + to_date are part of the key (not just institution +
        from_date) so multiple degrees from the same institution with no
        enrollment date — e.g. bachelor's + master's + a refresher course all at
        one university, all with from_date=None — derive DISTINCT ids instead of
        collapsing onto one MERGE node (the WR-01 rationale, applied to Education).
        """
        return hashlib.sha1(
            f"{document_id}|{institution}|{degree}|{field}|{from_date}|{to_date}".encode()
        ).hexdigest()

    @staticmethod
    def _contact_id(document_id: str, type_: str, value: str) -> str:
        """sha1(document_id|type|value) — deterministic, 40-char hex."""
        return hashlib.sha1(
            f"{document_id}|{type_}|{value}".encode()
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
        4. Experiences (nodes + company/edges + USED_SKILL)
        5. Education (nodes + Institution node/edges)
        6. Provenance edge (Candidate-[:SOURCED_FROM]->Document)
        """
        document_id = candidate_id  # same value; alias for clarity in provenance link

        # Timestamp stamped once per transaction (mirrors pdf.py line 175)
        now = dt.datetime.now(dt.UTC).isoformat()

        # Build skill union (D-04/D-05): .strip() + dedup, no lowercasing
        skills: set[str] = {s.strip() for s in candidate.skills}
        for exp in candidate.experiences:
            skills |= {s.strip() for s in exp.skills_mentioned}
        skills.discard("")  # remove empty strings if any

        # Derive each experience's normalized fields + deterministic id ONCE,
        # so the experience loop (4) and the worked_at Fact loop (6) stay in sync
        # (WR-02): skip experiences whose company/role are blank after strip —
        # they cannot form a meaningful node and would create garbage shared
        # Company/Role nodes keyed on "".
        processed_exps: list[tuple] = []
        for exp in candidate.experiences:
            company = exp.company.strip()
            role = exp.role.strip()
            if not company or not role:
                logger.warning(
                    "graph_writer: skipping experience with blank company/role "
                    "id={}",
                    candidate_id,
                )
                continue
            exp_id = self._experience_id(document_id, company, role, exp.from_date)
            processed_exps.append((exp, exp_id, company, role))

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
        for exp, exp_id, company, role in processed_exps:
            # Nodes — role is now a property on Experience (no shared Role node);
            # description is persisted for the semantic-search layer (v1.2+).
            await tx.run(MERGE_COMPANY, name=company, industry=None)
            await tx.run(
                MERGE_EXPERIENCE,
                id=exp_id,
                role=role,
                description=exp.description,
                from_date=exp.from_date,
                to_date=exp.to_date,
                is_current=exp.is_current,
            )

            # Edges
            await tx.run(LINK_HAS_EXPERIENCE, c_id=candidate_id, e_id=exp_id)
            await tx.run(LINK_AT_COMPANY, e_id=exp_id, name=company)

            # USED_SKILL edges (D-06): skills_mentioned in this role
            for s in exp.skills_mentioned:
                s = s.strip()
                if s:
                    await tx.run(LINK_USED_SKILL, e_id=exp_id, name=s)

        # ------------------------------------------------------------------
        # 5. Education (+ shared Institution node, mirroring Company)
        # ------------------------------------------------------------------
        for edu in candidate.education:
            edu_id = self._education_id(
                document_id,
                edu.institution,
                edu.degree,
                edu.field,
                edu.from_date,
                edu.to_date,
            )
            await tx.run(
                MERGE_EDUCATION,
                id=edu_id,
                degree=edu.degree,
                field=edu.field,
                from_date=edu.from_date,
                to_date=edu.to_date,
            )
            await tx.run(LINK_HAS_EDUCATION, c_id=candidate_id, ed_id=edu_id)

            # Institution is a shared node ("find graduates of X" = traversal).
            # Skip the link when the institution name is blank after strip —
            # same guard rationale as blank company/role (no garbage "" node).
            institution = edu.institution.strip() if edu.institution else ""
            if institution:
                await tx.run(MERGE_INSTITUTION, name=institution)
                await tx.run(LINK_AT_INSTITUTION, ed_id=edu_id, name=institution)

        # ------------------------------------------------------------------
        # 6. Provenance edge: Candidate-[:SOURCED_FROM]->Document
        # Replaces the reified Fact layer in the 1:1 world. Extraction metadata
        # (model_version, extracted_at) is stamped on the edge — it describes the
        # extraction event, not the person. T-06-05: model_version is the
        # caller-stamped value on the candidate, never produced by the LLM.
        # ------------------------------------------------------------------
        await tx.run(
            LINK_SOURCED_FROM,
            c_id=candidate_id,
            d_id=document_id,
            model_version=candidate.model_version,
            extracted_at=now,
        )
