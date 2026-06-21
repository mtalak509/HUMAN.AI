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
# Prompt template — production extractor prompt.
#
# Supersedes the verbatim rnd smoke-test prompt (rnd/src/openrouter_client.py).
# The smoke-test prompt validated the *approach* (json_object + Pydantic + retry);
# this version hardens it against the failure modes documented in
# rnd/smoke_test_findings.md and aligns field rules with what the downstream
# GraphWriter needs (shared Company/Institution nodes, Experience id keyed on
# company|role|from_date, degree used for filtering, skills = union).
#
# Design notes:
#   - The schema injected via {schema} is pruned of provenance (document_id,
#     model_version) and computed (is_current) fields — the model must NOT
#     produce them; they are stamped by _validate. See _extraction_schema().
#   - Rules are ordered: a single overriding principle (extract, never invent),
#     then per-field rules, then normalization rules that protect graph dedup.
# ---------------------------------------------------------------------------

PROMPT_TEMPLATE = """Ты — система точного извлечения структурированных данных из резюме \
кандидатов. Твой выход напрямую попадает в граф знаний рекрутинговой платформы, \
поэтому ценится точность и воспроизводимость, а не полнота любой ценой.

# Вход
Текст одного резюме, извлечённый из PDF постранично. Границы страниц помечены \
маркерами `--- PAGE N ---`. Возможны артефакты PDF-парсинга: склеенные слова, \
разорванные строки, перепутанный порядок колонок (двухколоночный layout), мусорные \
переносы, повторяющиеся колонтитулы. Восстанавливай смысл текста, но НЕ добавляй \
информацию, которой в тексте нет.

# Главный принцип
ИЗВЛЕКАЙ, А НЕ СОЧИНЯЙ. Если данных в тексте нет — оставляй поле пустым (null или \
[]), а не заполняй правдоподобной догадкой. Любое значение в выходе должно \
прослеживаться к конкретному месту в тексте резюме. Лучше пропустить факт, чем \
выдумать. При сомнении между «интерпретировать» и «оставить как есть» — оставляй \
ближе к тексту.

# Язык
Сохраняй язык источника: русское резюме → русские значения, английское → \
английские. Не переводи названия компаний, должностей, навыков и учебных заведений.

# Правила по полям
- full_name: полное имя кандидата как в резюме (обычно ФИО). Обязательное поле.
- contacts[]: каждый канал связи отдельным объектом {{type, value}}. type — один из \
  email | phone | telegram | linkedin | other. value — само значение, очищенное от \
  подписей и лишних символов ("Email: a@b.ru" → value "a@b.ru"). Не выдумывай \
  контакты; если канала нет — не добавляй объект. Если канал есть, но тип неясен — \
  type = "other".
- experiences[]: места работы, по одному объекту на позицию.
  - from_date / to_date: формат YYYY-MM, если известен месяц, иначе YYYY. НЕ выдумывай \
    месяц, которого нет в тексте, и НЕ выдумывай год. Бери ровно ту точность, что в \
    источнике.
  - to_date = null для текущего места работы («по настоящее время», «н.в.», \
    "present", "current"). НИКОГДА не подставляй текущую дату вместо null.
  - company: название компании-работодателя как в тексте.
  - role: должность в этой компании.
  - description: ПОЛНОЕ содержание обязанностей/достижений по этой роли, если оно \
    есть в тексте. Если описания в резюме нет — null (НЕ сочиняй описание).
  - skills_mentioned[]: ТОЛЬКО навыки/инструменты, явно упомянутые в описании именно \
    этой роли. Не переноси сюда навыки из других разделов и не додумывай.
  - Два периода в одной компании — это два отдельных объекта experiences (не \
    объединяй).
- education[]: образование, по одному объекту на запись.
  - institution: название учебного заведения как в тексте.
  - degree: уровень/тип квалификации как в источнике (например «Высшее», «Бакалавр», \
    «Магистр», «Среднее профессиональное», "MBA"). НЕ повышай уровень: колледж / \
    техникум / училище — это среднее профессиональное, НЕ «высшее». Если уровень не \
    указан — null.
  - field: специальность / направление подготовки, если указано, иначе null.
  - from_date / to_date: годы обучения по тем же правилам дат, иначе null.
- skills[]: сводный список всех навыков кандидата. Это ОБЪЕДИНЕНИЕ: и навыки из \
  отдельного раздела «Навыки/Skills», и ВСЕ навыки из skills_mentioned по всем ролям. \
  Ни один навык, попавший в skills_mentioned, не должен потеряться в skills. Убери \
  точные дубликаты, но не нормализуй и не переводи формулировки.

# Нормализация (защита от дублей в графе)
Компании (company) и учебные заведения (institution) — общие узлы графа, по ним \
ищут «кто работал в X» и «выпускники Y». Поэтому пиши их единообразно: только \
название, без приписок города/страны/организационно-правовой формы, если они не \
часть официального имени и не указаны в самом резюме рядом с названием. Не добавляй \
от себя «, Москва» и подобное. Одну и ту же компанию во всех записях называй \
одинаково.

# Формат вывода
Верни ТОЛЬКО валидный JSON-объект по схеме ниже. Без markdown-обёрток, без \
комментариев, без текста до или после JSON. Поля document_id и model_version в выход \
не включай — они проставляются системой.

JSON-схема ответа:
{schema}

Текст резюме:
---
{resume_text}
---"""


def _extraction_schema() -> dict:
    """ExtractedCandidate JSON schema pruned for the prompt.

    Removes fields the LLM must NOT produce:
      - provenance (document_id, model_version) — stamped by _validate (T-05-04).
      - is_current — a computed_field derived from to_date (defensive: not present
        in validation-mode schema, but pruned in case the mode changes).
    """
    schema = ExtractedCandidate.model_json_schema()

    props = schema.get("properties", {})
    required = schema.get("required", [])
    for field in ("document_id", "model_version"):
        props.pop(field, None)
        if field in required:
            required.remove(field)

    experience = schema.get("$defs", {}).get("Experience", {})
    exp_props = experience.get("properties", {})
    exp_required = experience.get("required", [])
    exp_props.pop("is_current", None)
    if "is_current" in exp_required:
        exp_required.remove("is_current")

    return schema


def _build_prompt(resume_text: str) -> str:
    """Build the extraction prompt with the pruned ExtractedCandidate schema injected.

    The provenance fields (document_id, model_version) and the computed is_current
    field are stripped from the schema shown to the LLM — the model should not
    generate them; provenance is stamped by _validate, is_current is derived.
    """
    schema_json = json.dumps(_extraction_schema(), ensure_ascii=False, indent=2)
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
