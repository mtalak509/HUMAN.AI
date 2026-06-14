"""core.pipeline.tasks — Celery task: process_document.

Orchestrates the full parse -> extract -> write pipeline for a single document.

Design decisions:
  D-01: Status D-01 minimal set: processing set at start, written on success.
  D-07: Fail-fast — NO Celery autoretry. Any stage exception marks the document
        failed (with failed_stage attribution) and propagates to Celery as a
        task failure. The extractor's own 1-retry is preserved (D-07).
  D-03: The Celery worker builds its own GraphDB from get_settings() — the
        scripts/ pattern. NOT FastAPI Depends (workers have no FastAPI app).

Security (T-07-01): All status updates use parameterized Cypher via status.py.
Security (T-07-02): document_id is a 64-char SHA-256 hex; PdfParser re-derives
                     it from the actual bytes — a forged id cannot point to
                     someone else's content.
Security (T-07-03): If Neo4j is unavailable, raises RuntimeError immediately —
                     never a silent "success with no data written" state.
Security (T-07-04): error text is truncated to 2000 chars before storage.
"""

import asyncio

from loguru import logger

from core.config import get_settings
from core.database.graph import GraphDB
from core.extractor.llm import Extractor
from core.parser.pdf import PdfParser
from core.pipeline.celery_app import celery_app
from core.pipeline.status import (
    STATUS_PROCESSING,
    STATUS_WRITTEN,
    set_failed,
    set_status,
)
from core.writer.graph_writer import GraphWriter

# Maximum length for stored error text (T-07-04: bounds storage, no api_key in path)
_MAX_ERROR_LEN = 2000


async def _record_failure(
    db: GraphDB, document_id: str, exc: Exception, stage: str
) -> None:
    """Best-effort failure recording (CR-01).

    Opens a fresh session to mark the document failed. If Neo4j dropped
    *during* a stage (e.g. mid LLM call), opening that session can itself raise.
    This helper catches its own errors and NEVER raises, so the caller can always
    re-raise the ORIGINAL stage exception. Without this, a recording-time error
    would mask the real cause and leave the document wedged at 'processing'
    forever (D-05 dedup then treats it as in-flight and refuses re-enqueue).
    """
    try:
        async with db.session() as s:
            await set_failed(s, document_id, str(exc)[:_MAX_ERROR_LEN], stage)
    except Exception as rec_exc:
        # Never let a recording failure escape — the original exc must surface.
        logger.error(
            "pipeline: could not record {} failure doc_id={} (Neo4j down?): {}",
            stage,
            document_id,
            rec_exc,
        )


async def _run(document_id: str) -> None:
    """Async orchestrator: parse -> extract -> write with per-stage error tracking.

    This is the inner async function; the Celery task wraps it with asyncio.run().

    Raises:
        RuntimeError: if Neo4j is unavailable (T-07-03 — never silent success).
        Any exception from parse / extract / write after recording it as a failure.
    """
    settings = get_settings()

    # Build own GraphDB (scripts pattern per CLAUDE.md — no FastAPI Depends in workers)
    db = GraphDB(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
    )
    await db.connect_with_retry()

    # T-07-03: if Neo4j is down, raise BEFORE any status write.
    # We cannot record status either — Celery records the exception instead.
    if not db.is_connected:
        raise RuntimeError(
            f"Neo4j unavailable — cannot run ingestion pipeline for {document_id}"
        )

    try:
        # Step 1: Mark document as processing
        async with db.session() as s:
            await set_status(s, document_id, STATUS_PROCESSING)
        logger.info("pipeline: processing started doc_id={}", document_id)

        # Step 2: Locate the stored PDF
        # The API (07-02) stores file_uri on the Document node; re-reading it from
        # the node requires an extra query. Instead, glob the storage directory —
        # the parser stores the PDF under documents/{document_id}/*.pdf.
        pdf_dir = settings.storage_root / "documents" / document_id
        pdf_candidates = list(pdf_dir.glob("*.pdf"))
        if not pdf_candidates:
            raise FileNotFoundError(
                f"No PDF found in storage for document_id={document_id} "
                f"(expected at {pdf_dir})"
            )
        pdf_path = pdf_candidates[0]

        # Step 3: Parse
        try:
            parser = PdfParser(db=db, storage_root=settings.storage_root)
            result = await parser.parse(pdf_path)
            logger.info(
                "pipeline: parse OK doc_id={} chars={}",
                document_id,
                len(result.extracted_text),
            )
        except Exception as exc:
            logger.error("pipeline: parse FAILED doc_id={} error={}", document_id, exc)
            await _record_failure(db, document_id, exc, "parse")
            raise

        # Step 4: Extract
        try:
            extractor = Extractor(settings=settings)
            candidate = await extractor.extract(result.extracted_text, document_id)
            logger.info("pipeline: extract OK doc_id={}", document_id)
        except Exception as exc:
            logger.error("pipeline: extract FAILED doc_id={} error={}", document_id, exc)
            await _record_failure(db, document_id, exc, "extract")
            raise

        # Step 5: Write to graph
        # GraphWriter has graceful degradation (silent return on no-db) but we have
        # confirmed db.is_connected above, so this will actually write.
        # Nonetheless, wrap in try/except to record write-stage failures.
        try:
            writer = GraphWriter(db=db, settings=settings)
            await writer.write(candidate, document_id)
            logger.info("pipeline: write OK doc_id={}", document_id)
        except Exception as exc:
            logger.error("pipeline: write FAILED doc_id={} error={}", document_id, exc)
            await _record_failure(db, document_id, exc, "write")
            raise

        # Step 6: Mark written
        async with db.session() as s:
            await set_status(s, document_id, STATUS_WRITTEN)
        logger.info("pipeline: pipeline complete doc_id={}", document_id)

    finally:
        await db.close()


@celery_app.task(name="process_document")  # type: ignore[untyped-decorator]
def process_document(document_id: str) -> None:
    """Celery task: orchestrate the full parse->extract->write pipeline.

    Fail-fast (D-07): NO autoretry_for. Any stage exception propagates to Celery
    as a task failure. The extractor's internal 1-retry is preserved unchanged.

    Args:
        document_id: 64-char SHA-256 hex of the uploaded PDF.
    """
    asyncio.run(_run(document_id))
