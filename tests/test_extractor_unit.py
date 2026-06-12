"""Unit tests for core.extractor.llm.Extractor.

Tests use a mocked OpenAI client — no network calls, no real API key required.
All async tests use session-scoped loop (per CLAUDE.md asyncio fixture pattern).

Behaviour tested:
  1. Successful extraction returns ExtractedCandidate with correct provenance.
  2. First response invalid (ValidationError) → retry called; second valid → success.
  3. Both responses invalid → ValidationError propagated (failure-policy: propagate).
  4. response_format in code == {"type": "json_object"} (not json_schema).
  5. client.chat.completions.create is offloaded via run_in_executor (async, non-blocking).
  6. Missing openrouter_api_key → RuntimeError on Extractor construction.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio  # noqa: F401

from core.config import Settings, get_settings
from core.extractor.llm import Extractor
from core.extractor.schema import ExtractedCandidate

pytestmark = pytest.mark.asyncio(loop_scope="session")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_JSON = json.dumps(
    {
        "full_name": "Ivan Ivanov",
        "contacts": [{"type": "email", "value": "ivan@example.com"}],
        "experiences": [
            {
                "from_date": "2020-01",
                "to_date": None,
                "company": "Acme Corp",
                "role": "Engineer",
                "description": "Built things",
                "skills_mentioned": ["Python"],
            }
        ],
        "education": [{"institution": "MIT", "degree": "BSc", "field": "CS"}],
        "skills": ["Python", "FastAPI"],
        # provenance fields — should be overridden by Extractor._validate
        "document_id": "llm-provided-id-should-be-ignored",
        "model_version": "llm-provided-model-should-be-ignored",
    }
)

_INVALID_JSON = json.dumps({"full_name": 123})  # full_name must be str — will fail Pydantic


def _make_response(content: str) -> MagicMock:
    """Build a minimal mock that mimics openai.types.chat.ChatCompletion."""
    msg = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=msg)
    return SimpleNamespace(choices=[choice])


def _make_settings(api_key: str = "sk-test-fake-key") -> Settings:
    """Return a Settings instance with a fake API key (bypasses .env validation)."""
    get_settings.cache_clear()
    return Settings(  # type: ignore[call-arg]
        neo4j_password="test",
        openrouter_api_key=api_key,
    )


# ---------------------------------------------------------------------------
# Test 1: successful extraction returns correct provenance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_success_returns_provenance() -> None:
    """extract() with valid JSON returns ExtractedCandidate; stamps provenance fields."""
    settings = _make_settings()
    extractor = Extractor(settings=settings)

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_response(_VALID_JSON)
    extractor._client = mock_client

    doc_id = "abc123"
    result = await extractor.extract(_VALID_JSON, doc_id)

    assert isinstance(result, ExtractedCandidate)
    # Provenance stamped by Extractor, NOT taken from LLM response
    assert result.document_id == doc_id
    assert result.model_version == settings.extractor_model
    # LLM-provided provenance fields should be overwritten
    assert result.document_id != "llm-provided-id-should-be-ignored"
    assert result.model_version != "llm-provided-model-should-be-ignored"
    # Data fields preserved
    assert result.full_name == "Ivan Ivanov"
    assert len(result.skills) == 2


# ---------------------------------------------------------------------------
# Test 2: retry on first ValidationError → second valid → success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_retry_on_validation_error() -> None:
    """First LLM response is invalid; second (retry) is valid — exactly 2 create() calls."""
    settings = _make_settings()
    extractor = Extractor(settings=settings)

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _make_response(_INVALID_JSON),  # first call: invalid
        _make_response(_VALID_JSON),    # second call (retry): valid
    ]
    extractor._client = mock_client

    result = await extractor.extract("some resume text", "doc-retry-test")

    assert isinstance(result, ExtractedCandidate)
    assert mock_client.chat.completions.create.call_count == 2

    # Verify retry prompt contains error info — check second call's user message
    second_call = mock_client.chat.completions.create.call_args_list[1]
    second_messages = second_call.kwargs.get("messages", [])
    user_msg = next((m for m in second_messages if m["role"] == "user"), None)
    assert user_msg is not None
    assert "Верни исправленный JSON по схеме" in user_msg["content"]


# ---------------------------------------------------------------------------
# Test 3: both responses invalid → ValidationError propagated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_propagates_on_second_failure() -> None:
    """Both LLM responses invalid → second ValidationError is raised (not silenced)."""
    from pydantic import ValidationError

    settings = _make_settings()
    extractor = Extractor(settings=settings)

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _make_response(_INVALID_JSON),
        _make_response(_INVALID_JSON),
    ]
    extractor._client = mock_client

    with pytest.raises(ValidationError):
        await extractor.extract("some resume text", "doc-propagate-test")

    assert mock_client.chat.completions.create.call_count == 2


# ---------------------------------------------------------------------------
# Test 4: response_format == {"type": "json_object"} (not json_schema)
# ---------------------------------------------------------------------------


def test_response_format_is_json_object() -> None:  # sync test — no asyncio mark needed
    """The _call method must use response_format={"type": "json_object"}."""
    settings = _make_settings()
    extractor = Extractor(settings=settings)

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_response(_VALID_JSON)
    extractor._client = mock_client

    extractor._call("test prompt")

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs.get("response_format") == {"type": "json_object"}, (
        f"Expected json_object format, got: {call_kwargs.get('response_format')}"
    )
    # Explicitly verify json_schema is NOT used
    assert call_kwargs.get("response_format", {}).get("type") != "json_schema"


# ---------------------------------------------------------------------------
# Test 5: extract() is async and offloads via run_in_executor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_uses_run_in_executor() -> None:
    """extract() must use asyncio.get_running_loop().run_in_executor (non-blocking)."""
    settings = _make_settings()
    extractor = Extractor(settings=settings)

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_response(_VALID_JSON)
    extractor._client = mock_client

    executor_called = []

    with patch("asyncio.get_running_loop") as mock_loop:
        inner_loop = MagicMock()
        # Make run_in_executor actually call the function synchronously for the test
        async def fake_run_in_executor(executor, fn, *args):  # type: ignore[no-untyped-def]
            executor_called.append((fn, args))
            return fn(*args)

        inner_loop.run_in_executor = fake_run_in_executor
        mock_loop.return_value = inner_loop

        result = await extractor.extract("resume text", "doc-executor-test")

    assert len(executor_called) >= 1, "run_in_executor must be called at least once"
    assert isinstance(result, ExtractedCandidate)


# ---------------------------------------------------------------------------
# Test 6: missing api_key → RuntimeError on construction
# ---------------------------------------------------------------------------


def test_missing_api_key_raises_runtime_error() -> None:
    """Extractor.__init__ raises RuntimeError when openrouter_api_key is None or empty."""
    get_settings.cache_clear()
    settings_no_key = Settings(  # type: ignore[call-arg]
        neo4j_password="test",
        openrouter_api_key=None,
    )

    with pytest.raises(RuntimeError) as exc_info:
        Extractor(settings=settings_no_key)

    error_msg = str(exc_info.value)
    assert "OPENROUTER_API_KEY" in error_msg
    # Must NOT include the actual key value (T-05-05)
    assert "sk-" not in error_msg
    assert "None" not in error_msg.lower() or "api_key" not in error_msg.lower()


def test_empty_api_key_raises_runtime_error() -> None:
    """Extractor.__init__ raises RuntimeError when openrouter_api_key is empty string."""
    get_settings.cache_clear()
    settings_empty_key = Settings(  # type: ignore[call-arg]
        neo4j_password="test",
        openrouter_api_key="",
    )

    with pytest.raises(RuntimeError) as exc_info:
        Extractor(settings=settings_empty_key)

    assert "OPENROUTER_API_KEY" in str(exc_info.value)
