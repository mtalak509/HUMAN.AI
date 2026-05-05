def test_models_imports_new_and_legacy_paths() -> None:
    from core import models as legacy_models
    from core.schemas import models as schema_models

    assert legacy_models.Candidate is schema_models.Candidate
    assert legacy_models.Skill is schema_models.Skill
