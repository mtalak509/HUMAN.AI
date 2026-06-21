from datetime import datetime

from pydantic import BaseModel, Field


class Candidate(BaseModel):
    id: str
    full_name: str
    status: str | None = Field(default=None)  # e.g. active, hired, rejected
    created_at: datetime | None = None


class Contact(BaseModel):
    id: str
    type: str | None = None  # email / phone / telegram
    value: str | None = None
    created_at: datetime | None = None


class Skill(BaseModel):
    name: str  # required — primary identifier
    canonical_name: str | None = None
    category: str | None = None
    created_at: datetime | None = None


class Company(BaseModel):
    name: str  # required — primary identifier
    canonical_name: str | None = None
    industry: str | None = None
    created_at: datetime | None = None


class Institution(BaseModel):
    name: str  # required — primary identifier (mirrors Company)
    canonical_name: str | None = None
    created_at: datetime | None = None


class Experience(BaseModel):
    id: str
    role: str | None = None  # job title (was a shared Role node before 2026-06-21)
    description: str | None = None  # free text — semantic-search payload (v1.2+)
    from_date: str | None = None  # renamed from "from" (Python keyword)
    to_date: str | None = None  # renamed from "to"; None means current
    is_current: bool | None = None
    created_at: datetime | None = None


class Education(BaseModel):
    id: str
    degree: str | None = None  # institution is now a separate Institution node
    field: str | None = None
    from_date: str | None = None  # ISO date string
    to_date: str | None = None
    created_at: datetime | None = None


class Vacancy(BaseModel):
    id: str
    title: str | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    status: str | None = None
    created_at: datetime | None = None


class Status(BaseModel):
    id: str
    name: str | None = None  # rejected / in_progress / offered / hired / withdrawn
    changed_at: datetime | None = None
    created_at: datetime | None = None


class HRNote(BaseModel):
    id: str
    author: str | None = None
    text: str | None = None
    created_at: datetime | None = None


class Document(BaseModel):
    id: str
    type: str | None = None  # resume / note / ats_field
    file_uri: str | None = None
    ingested_at: datetime | None = None
    created_at: datetime | None = None
    # --- added in Phase 4 (PDF parser) ---
    text_uri: str | None = None            # path to extracted .md text file
    parser_version: str | None = None      # e.g. "pypdf-v1"
    extraction_status: str | None = None   # "ok" | "empty"
    # --- added in Phase 7 (ingestion API) ---
    processing_status: str | None = None  # D-01: queued | processing | written | failed
    error: str | None = None              # D-06: exception text, set only on failure
    failed_stage: str | None = None       # D-06: parse | extract | write, set only on failure


# NOTE: the Role and Fact node types were removed in the 2026-06-21 graph refactor.
#   - Role → Experience.role (a free-form title is noise as a shared node).
#   - Fact → provenance moved to the Candidate-[:SOURCED_FROM]->Document edge.
# The Fact reification layer returns with entity resolution (v1.2), when a single
# candidate spans multiple source documents and claims can conflict / carry
# confidence. See docs/project_status.md §3 for the deviation record.
