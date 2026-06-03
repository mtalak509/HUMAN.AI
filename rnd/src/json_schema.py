from typing import Literal, Optional

from pydantic import BaseModel, Field


class Contact(BaseModel):
    type: Literal["email", "phone", "telegram", "linkedin", "other"]
    value: str


class Experience(BaseModel):
    from_date: str = Field(description="YYYY-MM или YYYY")
    to_date: Optional[str] = Field(default=None, description="None если по настоящее время")
    company: str
    role: str
    description: Optional[str] = None
    skills_mentioned: list[str] = Field(default_factory=list)


class Education(BaseModel):
    institution: str
    degree: Optional[str] = None
    field: Optional[str] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None


class Resume(BaseModel):
    full_name: str
    contacts: list[Contact] = Field(default_factory=list)
    experiences: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)