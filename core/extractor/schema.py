"""core.extractor.schema — Pydantic v2 contract for LLM extractor output.

Mirrors the rnd Resume schema (D-04: fields transferred verbatim) with two deltas:
  - D-05: Experience.is_current — computed_field derived from to_date is None.
  - D-02: ExtractedCandidate carries top-level provenance (document_id, model_version).

Fields are NOT renamed to match the graph ontology (D-06 — mapping deferred to Phase 6).
This schema is the trust boundary: LLM output (untrusted) → Pydantic validation (T-05-01).
"""

from typing import Literal

from pydantic import BaseModel, Field, computed_field


class Contact(BaseModel):
    """Single contact channel extracted from a resume."""

    type: Literal["email", "phone", "telegram", "linkedin", "other"]
    value: str


class Experience(BaseModel):
    """One work experience entry extracted from a resume.

    is_current is a computed_field: serialised in model_dump/JSON but NOT required
    from the LLM on input (it is derived from to_date is None).
    """

    from_date: str = Field(description="Start date in YYYY-MM or YYYY format")
    to_date: str | None = Field(
        default=None,
        description="End date in YYYY-MM or YYYY format; None means current position",
    )
    company: str
    role: str
    description: str | None = None
    skills_mentioned: list[str] = Field(
        default_factory=list,
        description="Skills explicitly mentioned in this role's description",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_current(self) -> bool:
        """True when this is a current (ongoing) position (to_date is None)."""
        return self.to_date is None


class Education(BaseModel):
    """One education entry extracted from a resume."""

    institution: str
    degree: str | None = None
    field: str | None = None
    from_date: str | None = None
    to_date: str | None = None


class ExtractedCandidate(BaseModel):
    """Full candidate record returned by the LLM extractor.

    Top-level provenance fields (D-02):
      - document_id: SHA-256 of the source PDF (links back to Document node in Neo4j).
      - model_version: OpenRouter model id used for extraction (audit trail).

    Resume fields are verbatim from the rnd Resume schema (D-04).
    """

    # Provenance (D-02) — required; set by the Extractor, not the LLM
    document_id: str = Field(description="SHA-256 hex of the source PDF document")
    model_version: str = Field(description="OpenRouter model id used for extraction")

    # Resume fields (D-04: verbatim from rnd/src/json_schema.py::Resume)
    full_name: str
    contacts: list[Contact] = Field(default_factory=list)
    experiences: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
