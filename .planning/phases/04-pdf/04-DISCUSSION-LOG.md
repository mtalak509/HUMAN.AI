# Phase 4: PDF-парсер - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-03
**Phase:** 04-pdf
**Areas discussed:** Каскад pypdf→pdfplumber, Формат сохранённого текста, Пустое извлечение

---

## Каскад pypdf→pdfplumber

| Option | Description | Selected |
|--------|-------------|----------|
| По порогу пустых страниц | pypdf на весь док; если доля пустых страниц > порога — pdfplumber на весь док | |
| Постраничный фолбэк | Каждая пустая у pypdf страница пере-извлекается pdfplumber индивидуально | |
| Всегда оба, брать длиннее | Извлекать обоими, выбирать более длинный результат | |

**User's choice:** Free-text — «Давай fallback пока пропустим. Оставим возможность, то есть заглушку поставим, но сейчас писать не будем. Не понятны критерии когда он должен срабатывать. Писать его сейчас — это тыкать в небо пальцем».
**Notes:** v1 = только pypdf + шов под будущий backend. pdfplumber-фолбэк → Deferred. Сужает Success Criteria #4 роадмапа («каскад») — отмечено в CONTEXT (D-03).

---

## Формат сохранённого текста

| Option | Description | Selected |
|--------|-------------|----------|
| Сохранять page-маркеры (.txt) | `--- PAGE i ---` как в rnd/src/pdf_parser.py | частично |
| Чистый текст | Без маркеров, страницы склеены | |
| Два файла | .raw.txt с маркерами + .txt чистый | |

**User's choice:** Free-text — «Я предлагаю уйти от txt к .md формату. И сохранять page-маркеры».
**Notes:** Итог — формат `.md` + сохранение page-маркеров `--- PAGE i ---`. text_uri → .md.

---

## Пустое извлечение (скан/image-only PDF)

| Option | Description | Selected |
|--------|-------------|----------|
| Document + флаг, не падать | Сохранить PDF, создать Document с extraction_status, текст пустой | ✓ |
| Кидать ошибку | parse() падает, ничего не пишем в граф | |
| Частичный + флаг | Сохранить что извлеклось, флаг 'partial' ниже порога полноты | |

**User's choice:** Document + флаг, не падать (рекомендованный).
**Notes:** Согласуется с graceful-философией; OCR позже добьёт документы с extraction_status=empty.

---

## Claude's Discretion

- **document_id = SHA-256(pdf_bytes)** — зона не выбрана для обсуждения; решение за Claude. Детерминированный id → идемпотентность через MERGE по `.id`.
- Storage-раскладка и формат URI внутри `/storage/documents/{document_id}/`.
- Sync vs async интерфейс `PdfParser.parse()`.
- Точный синтаксис page-маркера в `.md`.

## Deferred Ideas

- pdfplumber-фолбэк (каскад извлечения) — реализация отложена, шов закладывается.
- OCR для скан-PDF (PARSE-05) — вне v1.1.
