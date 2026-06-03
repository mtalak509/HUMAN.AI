"""
[DEPRECATED] USE core.schemas.models instead.
Backward-compatible re-export for legacy ``core.models`` imports.
"""

from core.schemas.models import (
    Candidate,
    Company,
    Contact,
    Document,
    Education,
    Experience,
    Fact,
    HRNote,
    Role,
    Skill,
    Status,
    Vacancy,
)

__all__ = [
    "Candidate",
    "Company",
    "Contact",
    "Document",
    "Education",
    "Experience",
    "Fact",
    "HRNote",
    "Role",
    "Skill",
    "Status",
    "Vacancy",
]
