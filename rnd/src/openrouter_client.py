import json
import os
from typing import Optional

from dotenv import load_dotenv
from loguru import logger
from openai import OpenAI
from pydantic import ValidationError

try:
    from .json_schema import Resume
except ImportError:
    from json_schema import Resume

load_dotenv()


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


class OpenRouterClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "qwen/qwen3.6-plus",
        timeout: float = 60.0,
    ):
        api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Add it to rnd/.env or pass api_key explicitly."
            )

        self.client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            timeout=timeout,
            default_headers={
                "HTTP-Referer": "http://localhost",
                "X-Title": "human-ai-extractor-smoke",
            },
        )
        self.model = model

    @staticmethod
    def _build_prompt(resume_text: str) -> str:
        schema_json = json.dumps(Resume.model_json_schema(), ensure_ascii=False, indent=2)
        return PROMPT_TEMPLATE.format(schema=schema_json, resume_text=resume_text)

    def _call(self, prompt: str) -> str:
        logger.info(
            "LLM call: model={}, mode=json_object, prompt_chars={}",
            self.model,
            len(prompt),
        )
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": "Return only a valid JSON object matching the requested schema. No markdown, no commentary.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        logger.info(
            "LLM response: response_chars={}, usage={}",
            len(content),
            usage.model_dump() if usage is not None else "n/a",
        )
        return content

    def _call_structured(self, prompt: str, strict: bool = False) -> str:
        logger.info(
            "LLM call: model={}, mode=json_schema, strict={}, prompt_chars={}",
            self.model,
            strict,
            len(prompt),
        )
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": "Return only a valid JSON object matching the requested schema. No markdown, no commentary.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "Resume",
                    "strict": strict,
                    "schema": Resume.model_json_schema(),
                },
            },
        )
        content = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        logger.info(
            "LLM response: response_chars={}, usage={}",
            len(content),
            usage.model_dump() if usage is not None else "n/a",
        )
        return content

    def extract_resume_structured(
        self, resume_text: str, strict: bool = False
    ) -> tuple[Resume, str]:
        """Extract resume using OpenRouter structured outputs (json_schema).

        Will raise from the provider if the model does not support
        response_format=json_schema. Set strict=True for constrained
        decoding (requires schema to satisfy strict-mode rules).
        """
        logger.info(
            "extract_resume_structured: resume_chars={}, strict={}",
            len(resume_text),
            strict,
        )
        prompt = self._build_prompt(resume_text)
        raw = self._call_structured(prompt, strict=strict)
        parsed = Resume.model_validate_json(raw)
        logger.info(
            "extract_resume_structured: OK — name='{}', exp={}, edu={}, skills={}",
            parsed.full_name,
            len(parsed.experiences),
            len(parsed.education),
            len(parsed.skills),
        )
        return parsed, raw

    def extract_resume(self, resume_text: str) -> tuple[Resume, str]:
        """Extract resume; returns (parsed, raw_text). One retry on validation failure."""
        logger.info("extract_resume: resume_chars={}", len(resume_text))
        prompt = self._build_prompt(resume_text)
        raw = self._call(prompt)
        try:
            parsed = Resume.model_validate_json(raw)
        except ValidationError as e:
            logger.warning(
                "extract_resume: ValidationError on first attempt, retrying. errors={}",
                e.error_count(),
            )
            retry_prompt = (
                prompt
                + "\n\nПредыдущий ответ не прошёл валидацию по схеме. Ошибки:\n"
                + str(e)
                + "\n\nВерни исправленный JSON по схеме."
            )
            raw_retry = self._call(retry_prompt)
            parsed = Resume.model_validate_json(raw_retry)
            raw = raw_retry
        logger.info(
            "extract_resume: OK — name='{}', exp={}, edu={}, skills={}",
            parsed.full_name,
            len(parsed.experiences),
            len(parsed.education),
            len(parsed.skills),
        )
        return parsed, raw