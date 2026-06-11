"""Tests for core.extractor.schema — ExtractedCandidate Pydantic v2 model.

TDD: RED phase — tests written before implementation.
No infra required; all tests are pure Python/Pydantic.
"""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError  # noqa: F401

# ---------------------------------------------------------------------------
# Task 1: Schema tests
# ---------------------------------------------------------------------------


class TestContact:
    def test_valid_email(self):
        from core.extractor.schema import Contact

        c = Contact(type="email", value="a@b.c")
        assert c.type == "email"
        assert c.value == "a@b.c"

    def test_invalid_type_raises(self):
        from core.extractor.schema import Contact

        with pytest.raises(ValidationError):
            Contact(type="garbage", value="x")

    def test_all_valid_types(self):
        from core.extractor.schema import Contact

        for t in ("email", "phone", "telegram", "linkedin", "other"):
            c = Contact(type=t, value="v")
            assert c.type == t


class TestExperience:
    def test_is_current_true_when_to_date_none(self):
        from core.extractor.schema import Experience

        exp = Experience(from_date="2021-08", to_date=None, company="X", role="Y")
        assert exp.is_current is True

    def test_is_current_false_when_to_date_set(self):
        from core.extractor.schema import Experience

        exp = Experience(from_date="2020-01", to_date="2024-11", company="A", role="B")
        assert exp.is_current is False

    def test_is_current_serialized_in_model_dump(self):
        """is_current must appear in model_dump (computed_field, not just property)."""
        from core.extractor.schema import Experience

        exp = Experience(from_date="2021-08", company="X", role="Y")
        d = exp.model_dump()
        assert "is_current" in d
        assert d["is_current"] is True

    def test_skills_mentioned_defaults_to_empty(self):
        from core.extractor.schema import Experience

        exp = Experience(from_date="2020", company="C", role="R")
        assert exp.skills_mentioned == []

    def test_description_optional(self):
        from core.extractor.schema import Experience

        exp = Experience(from_date="2020", company="C", role="R")
        assert exp.description is None


class TestEducation:
    def test_minimal_valid(self):
        from core.extractor.schema import Education

        edu = Education(institution="MIT")
        assert edu.institution == "MIT"
        assert edu.degree is None
        assert edu.field is None
        assert edu.from_date is None
        assert edu.to_date is None

    def test_full_valid(self):
        from core.extractor.schema import Education

        edu = Education(
            institution="MSU",
            degree="Bachelor",
            field="Physics",
            from_date="1994",
            to_date="1999",
        )
        assert edu.degree == "Bachelor"


class TestExtractedCandidate:
    def test_minimal_valid_with_provenance(self):
        from core.extractor.schema import ExtractedCandidate

        c = ExtractedCandidate(
            full_name="N",
            document_id="abc",
            model_version="qwen/x",
        )
        assert c.full_name == "N"
        assert c.document_id == "abc"
        assert c.model_version == "qwen/x"

    def test_default_empty_lists(self):
        from core.extractor.schema import ExtractedCandidate

        c = ExtractedCandidate(full_name="N", document_id="d", model_version="m")
        assert c.contacts == []
        assert c.experiences == []
        assert c.education == []
        assert c.skills == []

    def test_model_fields_keys(self):
        from core.extractor.schema import ExtractedCandidate

        keys = set(ExtractedCandidate.model_fields.keys())
        assert "full_name" in keys
        assert "contacts" in keys
        assert "experiences" in keys
        assert "education" in keys
        assert "skills" in keys
        assert "document_id" in keys
        assert "model_version" in keys


# ---------------------------------------------------------------------------
# Equivalence test: all 5 rnd/data/results/*.parsed.json must validate
# ---------------------------------------------------------------------------


class TestParsedJsonEquivalence:
    """Validate that all reference parsed.json files conform to ExtractedCandidate.

    The parsed.json files don't contain is_current/document_id/model_version —
    those are injected during validation to simulate extractor output.
    """

    def _results_dir(self) -> Path:
        # Works from repo root (pytest run from C:/dev/HUMAN.AI)
        return Path("rnd/data/results")

    def test_all_parsed_json_files_found(self):
        files = list(self._results_dir().glob("*.parsed.json"))
        assert len(files) == 5, f"Expected 5 parsed.json files, found {len(files)}: {files}"

    @pytest.mark.parametrize(
        "json_file",
        list(Path("rnd/data/results").glob("*.parsed.json")),
        ids=lambda p: p.stem,
    )
    def test_parsed_json_validates(self, json_file: Path):
        from core.extractor.schema import ExtractedCandidate

        data = json.loads(json_file.read_text(encoding="utf-8"))
        # Inject provenance fields (not present in rnd outputs)
        candidate = ExtractedCandidate.model_validate(
            {**data, "document_id": "test-doc-id", "model_version": "test-model"}
        )
        assert candidate.full_name  # non-empty name
        # is_current correctly computed on each experience
        for exp in candidate.experiences:
            expected = exp.to_date is None
            assert exp.is_current is expected


# ---------------------------------------------------------------------------
# Task 2: Settings extractor config defaults
# ---------------------------------------------------------------------------


class TestExtractorSettingsDefaults:
    """Verify Settings contains extractor config knobs with smoke-test defaults."""

    def test_extractor_model_default(self):
        from core.config import get_settings

        get_settings.cache_clear()
        s = get_settings()
        assert s.extractor_model == "qwen/qwen3.6-plus"

    def test_openrouter_base_url_default(self):
        from core.config import get_settings

        get_settings.cache_clear()
        s = get_settings()
        assert s.openrouter_base_url == "https://openrouter.ai/api/v1"

    def test_extractor_timeout_default(self):
        from core.config import get_settings

        get_settings.cache_clear()
        s = get_settings()
        assert s.extractor_timeout == 60.0

    def test_extractor_temperature_default(self):
        from core.config import get_settings

        get_settings.cache_clear()
        s = get_settings()
        assert s.extractor_temperature == 0.0

    def test_openrouter_api_key_not_duplicated(self):
        """openrouter_api_key must appear exactly once in Settings."""
        from core.config import Settings

        # Only one field named openrouter_api_key
        matching = [k for k in Settings.model_fields if k == "openrouter_api_key"]
        assert len(matching) == 1
