def test_models_imports_new_and_legacy_paths() -> None:
    from core import models as legacy_models
    from core.schemas import models as schema_models

    assert legacy_models.Candidate is schema_models.Candidate
    assert legacy_models.Skill is schema_models.Skill


def test_document_d09_fields_via_both_import_paths() -> None:
    """D-09: text_uri, parser_version, extraction_status reachable from both import paths."""
    from core.models import Document as LegacyDocument
    from core.schemas.models import Document as SchemaDocument

    # Verify new fields exist in model_fields for both paths
    assert {"text_uri", "parser_version", "extraction_status"} <= set(SchemaDocument.model_fields)
    assert {"text_uri", "parser_version", "extraction_status"} <= set(LegacyDocument.model_fields)

    # Verify round-trip construction and field values via legacy path
    d_legacy = LegacyDocument(
        id="x",
        text_uri="documents/abc/text.md",
        parser_version="pypdf-v1",
        extraction_status="ok",
    )
    assert d_legacy.text_uri == "documents/abc/text.md"
    assert d_legacy.parser_version == "pypdf-v1"
    assert d_legacy.extraction_status == "ok"

    # Verify round-trip construction and field values via schema path
    d_schema = SchemaDocument(
        id="x",
        text_uri="documents/abc/text.md",
        parser_version="pypdf-v1",
        extraction_status="ok",
    )
    assert d_schema.text_uri == "documents/abc/text.md"
    assert d_schema.parser_version == "pypdf-v1"
    assert d_schema.extraction_status == "ok"

    # Both paths resolve to the same class
    assert LegacyDocument is SchemaDocument
