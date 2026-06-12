"""Integration tests for core.extractor.llm.Extractor — live equivalence against reference data.

LIVE TEST — requires OPENROUTER_API_KEY set in .env.
Skips cleanly when the key is absent (safe for CI without credentials).

Each test hits OpenRouter API and costs tokens. Run intentionally:
    pytest tests/test_extractor_integration.py -v

What is verified (success criterion #4 and #5 from 05-02-PLAN.md):
  - 0 ValidationError across 5 reference resumes (rnd/data/resume/*.pdf)
  - candidate.full_name matches etalon exactly
  - candidate.document_id stamped correctly (D-02)
  - candidate.model_version == extractor_model from Settings (D-03)
  - len(experiences) and len(education) within tolerance of etalon counts
  - candidate has at least 50% of etalon skills (lenient due to LLM non-determinism)

Comparison approach: temperature=0 gives stable LLM output but NOT byte-for-byte identical
to the rnd baseline (different schema, different model invocation context). The rnd baseline
used the rnd Resume schema; this extractor uses ExtractedCandidate. Minor variations in skill
naming and count are expected and acceptable. We assert invariants, not exact reproduction.

Tolerance choices (documented per plan instruction "выбери ассерт по факту прогона"):
  - full_name: exact match (most stable field)
  - experiences count: exact (LLM counts jobs reliably)
  - education count: ±1 tolerance (LLM sometimes splits compound degrees)
  - skills: candidate must cover ≥50% of etalon skills (LLM may rename/merge skills)
  - provenance: exact (stamped by Extractor, not LLM-generated)
"""

import json
from pathlib import Path

import pytest

from core.config import get_settings
from core.extractor.llm import Extractor
from core.extractor.schema import ExtractedCandidate
from core.parser.pdf import PdfParser

# ---------------------------------------------------------------------------
# Skip gate — mirror of parser integration skip-on-no-neo4j pattern
# ---------------------------------------------------------------------------

get_settings.cache_clear()
_SETTINGS = get_settings()
_HAS_KEY = bool(_SETTINGS.openrouter_api_key)

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        not _HAS_KEY,
        reason="OPENROUTER_API_KEY not set — live LLM test skipped",
    ),
]

# ---------------------------------------------------------------------------
# Reference data paths
# ---------------------------------------------------------------------------

_RESUME_DIR = Path("rnd/data/resume")
_RESULTS_DIR = Path("rnd/data/results")

# Explicit list of 5 reference resumes (must match rnd/data/resume/*.pdf)
_RESUME_NAMES = ["Talakin", "Talakina", "Suhanova", "Markova", "Denisenko"]


def _load_etalon(name: str) -> dict:  # type: ignore[type-arg]
    """Load the reference parsed.json for a resume by name (without extension)."""
    path = _RESULTS_DIR / f"{name}.parsed.json"
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Parametrised live equivalence test
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("resume_name", _RESUME_NAMES)
async def test_extractor_equivalence_against_etalon(
    resume_name: str, tmp_path: Path
) -> None:
    """Live test: extract resume, verify 0 ValidationError + key-field equivalence.

    Primary verification (must always pass):
      1. No ValidationError (implicit — if extract() raises, test fails)
      2. candidate.document_id == parse_result.document_id (D-02 provenance)
      3. candidate.model_version == Settings.extractor_model (D-03 provenance)
      4. full_name matches etalon exactly (most stable field, temperature=0)

    Soft verification (documented tolerance, see module docstring):
      5. len(experiences) == etalon count (LLM counts jobs reliably)
      6. len(education) within ±1 of etalon count (LLM may split compound degrees)
      7. candidate.skills overlap with etalon skills ≥ 50% (renames/merges acceptable)
    """
    pdf_path = _RESUME_DIR / f"{resume_name}.pdf"
    etalon = _load_etalon(resume_name)

    # Step 1: get plain text + document_id via PdfParser (db=None — no Neo4j needed)
    parser = PdfParser(db=None, storage_root=tmp_path)
    parse_result = await parser.parse(pdf_path)

    # Step 2: extract via live LLM — must not raise ValidationError
    extractor = Extractor()
    candidate: ExtractedCandidate = await extractor.extract(
        parse_result.extracted_text,
        document_id=parse_result.document_id,
    )

    # --- Primary assertions (criterion #4, #5 from plan) ---

    # Provenance stamped correctly (criterion #5)
    assert candidate.document_id == parse_result.document_id, (
        f"[{resume_name}] document_id mismatch: "
        f"got={candidate.document_id!r}, expected={parse_result.document_id!r}"
    )
    assert candidate.model_version == _SETTINGS.extractor_model, (
        f"[{resume_name}] model_version mismatch: "
        f"got={candidate.model_version!r}, expected={_SETTINGS.extractor_model!r}"
    )

    # full_name exact match (criterion #4 — key field)
    assert candidate.full_name == etalon["full_name"], (
        f"[{resume_name}] full_name mismatch: "
        f"got={candidate.full_name!r}, expected={etalon['full_name']!r}"
    )

    # --- Soft assertions (documented tolerance) ---

    # experiences count: exact (LLM reliably counts job entries)
    etalon_exp_count = len(etalon.get("experiences", []))
    assert len(candidate.experiences) == etalon_exp_count, (
        f"[{resume_name}] experiences count mismatch: "
        f"got={len(candidate.experiences)}, expected={etalon_exp_count}"
    )

    # education count: ±1 tolerance (LLM may split or merge degree entries)
    etalon_edu_count = len(etalon.get("education", []))
    edu_diff = abs(len(candidate.education) - etalon_edu_count)
    assert edu_diff <= 1, (
        f"[{resume_name}] education count diverges by more than 1: "
        f"got={len(candidate.education)}, expected={etalon_edu_count}"
    )

    # Skills coverage: candidate must cover at least 50% of etalon skills
    # (LLM may rename/merge/expand skills — "E-com Strategy" → "E-commerce Strategy")
    etalon_skills = set(etalon.get("skills", []))
    if etalon_skills:
        candidate_skills = set(candidate.skills)
        overlap = len(etalon_skills & candidate_skills)
        coverage = overlap / len(etalon_skills)
        assert coverage >= 0.5, (
            f"[{resume_name}] skills coverage too low: {coverage:.0%} "
            f"({overlap}/{len(etalon_skills)} etalon skills matched)\n"
            f"missing: {sorted(etalon_skills - candidate_skills)}\n"
            f"candidate: {sorted(candidate_skills)}"
        )
