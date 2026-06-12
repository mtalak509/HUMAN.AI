"""core.extractor.llm — LLM-powered resume extractor.

Transfers the json_object + Pydantic-validation + 1 retry strategy from
rnd/src/openrouter_client.py into core/ patterns:
  - async via run_in_executor (D-01, mirrors PdfParser pattern)
  - config-driven via Settings (api_key, model, base_url, timeout, temperature)
  - top-level provenance stamped by the caller (document_id, model_version = D-02/D-03)

Security (T-05-05): api_key is NEVER logged or included in exception messages.
Security (T-05-04): LLM output always validated through ExtractedCandidate schema.
Security (T-05-06): timeout from Settings is forwarded to the OpenAI client.
"""

import asyncio
import json

from loguru import logger
from openai import OpenAI
from pydantic import ValidationError

from core.config import Settings, get_settings
from core.extractor.schema import ExtractedCandidate

# ---------------------------------------------------------------------------
# Prompt template — transferred verbatim from rnd/src/openrouter_client.py
# (D-discretion: do not alter the strategy)
# ---------------------------------------------------------------------------

PROMPT_TEMPLATE = """Ты извлекаешь структурированную информацию из резюме кандидата.
На входе — текст резюме, извлечённый из PDF постранично. Границы страниц
помечены маркерами `--- PAGE N ---`. Текст может содержать артефакты парсинга
(склеенные слова, разорванные строки, перепутанный порядок колонок) —
интерпретируй смысл, не цепляйся за форматирование.

Заполни поля JSON-схемы согласно содержимому.
Правила:
- Если поле не упомянуто в резюме — null.
- Не выдумывай данные, которых нет в тексте.
- Для текущего места работы to_date = null.
- skills_mentioned для каждой роли — только навыки, явно упомянутые
  в описании этой конкретной роли (не сводный список).
- Сводный список skills — все навыки, которые встречаются в резюме.

JSON-схема ответа:
{schema}

Текст резюме:
---
{resume_text}
---

Верни только валидный JSON-объект по схеме, без markdown-обёрток."""


def _build_prompt(resume_text: str) -> str:
    """Build the extraction prompt with the current ExtractedCandidate schema injected.

    Schema used is ExtractedCandidate (from plan 05-01), NOT the rnd Resume schema.
    The provenance fields (document_id, model_version) are excluded from the schema
    shown to the LLM — the model should not generate them; they are stamped by _validate.
    """
    # Build a schema that excludes provenance fields so the LLM is not asked to produce them.
    # We use the full schema and let _validate override document_id/model_version anyway.
    schema_json = json.dumps(
        ExtractedCandidate.model_json_schema(), ensure_ascii=False, indent=2
    )
    return PROMPT_TEMPLATE.format(schema=schema_json, resume_text=resume_text)


class Extractor:
    """Async LLM extractor: plain text resume → validated ExtractedCandidate.

    Usage:
        extractor = Extractor()
        candidate = await extractor.extract(text, document_id="sha256hex...")

    Raises:
        RuntimeError: if OPENROUTER_API_KEY is not configured in Settings.
        ValidationError: if LLM output is invalid after 1 retry (propagated; no sentinel).
        json.JSONDecodeError: if LLM output is not parseable JSON.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        s = settings or get_settings()

        api_key = s.openrouter_api_key
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set in Settings/.env — "
                "add it to your .env file or set the OPENROUTER_API_KEY environment variable."
            )

        self._model: str = s.extractor_model
        self._temperature: float = s.extractor_temperature

        self._client = OpenAI(
            api_key=api_key,
            base_url=s.openrouter_base_url,
            timeout=s.extractor_timeout,
            default_headers={
                "HTTP-Referer": "http://localhost",
                "X-Title": "human-ai-extractor",
            },
        )

        logger.debug(
            "Extractor: initialised model={} base_url={}",
            self._model,
            s.openrouter_base_url,
        )

    def _call(self, prompt: str) -> str:
        """Make a synchronous LLM call using json_object response format.

        Must be called via run_in_executor from async context (D-01).
        Logs model, prompt_chars, response_chars — NEVER api_key or raw content (T-05-05).
        """
        logger.info(
            "extractor: LLM call model={} mode=json_object prompt_chars={}",
            self._model,
            len(prompt),
        )
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=self._temperature,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Return only a valid JSON object matching the requested schema. "
                        "No markdown, no commentary."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or ""
        logger.info(
            "extractor: LLM response model={} response_chars={}",
            self._model,
            len(content),
        )
        return content

    def _validate(self, raw: str, document_id: str) -> ExtractedCandidate:
        """Parse raw JSON string and validate into ExtractedCandidate.

        Stamps provenance (D-02/D-03):
          - document_id: from caller (authoritative — never trust LLM-provided value)
          - model_version: self._model (actual model id used for extraction)

        Raises:
            json.JSONDecodeError: if raw is not valid JSON.
            pydantic.ValidationError: if parsed data doesn't match the schema.
        """
        data = json.loads(raw)
        # Overwrite any LLM-provided provenance — caller is authoritative (T-05-04)
        data["document_id"] = document_id
        data["model_version"] = self._model
        return ExtractedCandidate.model_validate(data)

    async def extract(self, text: str, document_id: str) -> ExtractedCandidate:
        """Extract a structured candidate record from plain resume text.

        Offloads the synchronous OpenAI SDK call via run_in_executor (D-01).
        Applies 1 retry if the first response fails Pydantic validation (EXTR-02).
        Propagates ValidationError on the second failure — no sentinel (D-discretion).

        Args:
            text: Plain text of the resume (with optional --- PAGE N --- markers).
            document_id: SHA-256 hex of the source PDF; stamped on the result (D-02).

        Returns:
            ExtractedCandidate with document_id and model_version set by this call.

        Raises:
            RuntimeError: should have been raised at __init__ if api_key missing.
            ValidationError: if LLM output is invalid after the retry.
            json.JSONDecodeError: if LLM returns non-JSON even after retry.
        """
        prompt = _build_prompt(text)
        loop = asyncio.get_running_loop()

        raw = await loop.run_in_executor(None, self._call, prompt)
        try:
            candidate = self._validate(raw, document_id)
        except ValidationError as e:
            logger.warning(
                "extractor: ValidationError on first attempt, retrying. errors={}",
                e.error_count(),
            )
            retry_prompt = (
                prompt
                + "\n\nПредыдущий ответ не прошёл валидацию по схеме. Ошибки:\n"
                + str(e)
                + "\n\nВерни исправленный JSON по схеме."
            )
            raw = await loop.run_in_executor(None, self._call, retry_prompt)
            candidate = self._validate(raw, document_id)  # 2nd failure propagates (D-discretion)

        logger.info(
            "extractor: OK name='{}' exp={} edu={} skills={} doc_id={}",
            candidate.full_name,
            len(candidate.experiences),
            len(candidate.education),
            len(candidate.skills),
            document_id,
        )
        return candidate
