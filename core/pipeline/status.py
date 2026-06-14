"""core.pipeline.status — Pipeline status constants and Neo4j Cypher helpers.

Provides:
  - Status string constants for the Document.processing_status D-01 set
  - Parameterized Cypher helpers for all status transitions
  - All helpers take an open neo4j.AsyncSession (caller owns the session)

Security (T-07-01): ALL Cypher uses bound $params — NO f-string interpolation.
                    Document MERGE/MATCH uses .id only (document_id_unique constraint).
"""

import datetime as dt

from neo4j import AsyncSession

# ---------------------------------------------------------------------------
# Status constants (D-01 minimal set)
# ---------------------------------------------------------------------------

STATUS_QUEUED: str = "queued"
STATUS_PROCESSING: str = "processing"
STATUS_WRITTEN: str = "written"
STATUS_FAILED: str = "failed"

# ---------------------------------------------------------------------------
# Cypher statements (T-07-01: bound parameters, no f-strings)
# ---------------------------------------------------------------------------

# queued: MERGE on Document.id (canonical key per CLAUDE.md + document_id_unique constraint)
# ON CREATE SET — so a re-POST of a still-processing doc does not clobber in-flight status (D-05)
_MERGE_QUEUED_CYPHER = """
MERGE (d:Document {id: $document_id})
ON CREATE SET
    d.processing_status = $queued,
    d.file_uri = $file_uri,
    d.ingested_at = $now
"""

_SET_STATUS_CYPHER = """
MATCH (d:Document {id: $document_id})
SET d.processing_status = $status
"""

_SET_FAILED_CYPHER = """
MATCH (d:Document {id: $document_id})
SET d.processing_status = $failed,
    d.error = $error,
    d.failed_stage = $failed_stage
"""

_RESET_FOR_REQUEUE_CYPHER = """
MATCH (d:Document {id: $document_id})
SET d.processing_status = $queued,
    d.error = null,
    d.failed_stage = null
"""

# ---------------------------------------------------------------------------
# Async helpers — caller owns and passes the open AsyncSession
# ---------------------------------------------------------------------------


async def merge_document_queued(
    session: AsyncSession,
    document_id: str,
    file_uri: str,
) -> None:
    """MERGE a Document node keyed on document_id and mark it queued.

    Uses ON CREATE SET so a re-POST of an in-flight document does not overwrite
    its current processing_status (D-05 reuse behaviour).

    Args:
        session: Open Neo4j AsyncSession (caller owns lifecycle).
        document_id: 64-char SHA-256 hex — the only valid MERGE key for Document.
        file_uri: Relative path to the stored PDF (stored for the task to locate it).
    """
    now = dt.datetime.now(dt.UTC).isoformat()
    await session.run(
        _MERGE_QUEUED_CYPHER,
        document_id=document_id,
        file_uri=file_uri,
        queued=STATUS_QUEUED,
        now=now,
    )


async def set_status(
    session: AsyncSession,
    document_id: str,
    status: str,
) -> None:
    """Set Document.processing_status to the given status string.

    Args:
        session: Open Neo4j AsyncSession.
        document_id: 64-char SHA-256 hex of the document.
        status: One of STATUS_QUEUED / STATUS_PROCESSING / STATUS_WRITTEN / STATUS_FAILED.
    """
    await session.run(
        _SET_STATUS_CYPHER,
        document_id=document_id,
        status=status,
    )


async def set_failed(
    session: AsyncSession,
    document_id: str,
    error: str,
    failed_stage: str,
) -> None:
    """Mark Document as failed with error text and the failing stage name (D-06).

    Args:
        session: Open Neo4j AsyncSession.
        document_id: 64-char SHA-256 hex of the document.
        error: Exception message (truncated to 2000 chars by caller).
        failed_stage: One of "parse" | "extract" | "write".
    """
    await session.run(
        _SET_FAILED_CYPHER,
        document_id=document_id,
        failed=STATUS_FAILED,
        error=error,
        failed_stage=failed_stage,
    )


async def reset_for_requeue(
    session: AsyncSession,
    document_id: str,
) -> None:
    """Reset a failed Document back to queued state, clearing failure diagnostics (D-05/D-06).

    Used by the API re-enqueue branch so that a re-queued document never carries
    the previous failure's error/failed_stage (D-06 freshness).

    Args:
        session: Open Neo4j AsyncSession.
        document_id: 64-char SHA-256 hex of the document.
    """
    await session.run(
        _RESET_FOR_REQUEUE_CYPHER,
        document_id=document_id,
        queued=STATUS_QUEUED,
    )
