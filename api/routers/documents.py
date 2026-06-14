"""api.routers.documents — POST /documents and GET /documents/{document_id} endpoints.

API-01: POST /documents
  - Accept multipart/form-data with field "file" (PDF only)
  - Compute document_id = SHA-256(bytes) — same formula as PdfParser (idempotent)
  - Save raw PDF to {storage_root}/documents/{document_id}/{safe_name}
  - MERGE Document(processing_status=queued) in Neo4j BEFORE enqueue (D-04)
  - Enqueue process_document.delay(document_id)
  - Status-smart dedup (D-05): skip re-enqueue if already written/queued/processing

API-02: GET /documents/{document_id}
  - Return current processing_status + error + failed_stage from Document node (D-06)
  - 404 if document_id has no node

Security:
  T-07-06: MAX_UPLOAD_BYTES = 10 MiB cap -> 413
  T-07-07: Path(filename).name traversal guard before any disk write
  T-07-08: .pdf suffix + content-type validation -> 415
  T-07-09: document_id only used as a bound Cypher $param in GET (no injection)
"""

import hashlib
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse
from loguru import logger

from api.dependencies import get_db, get_settings
from core.database.graph import GraphDB
from core.pipeline.status import (
    STATUS_FAILED,
    STATUS_PROCESSING,
    STATUS_QUEUED,
    STATUS_WRITTEN,
    merge_document_queued,
    reset_for_requeue,
)
from core.pipeline.tasks import process_document

router = APIRouter()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# T-07-06: Reject uploads larger than this to bound memory/disk per request
MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024  # 10 MiB

# Accepted content-type values for PDF uploads (T-07-08)
_ACCEPTED_CONTENT_TYPES = frozenset({"application/pdf", "application/octet-stream"})

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_READ_STATUS_CYPHER = """
MATCH (d:Document {id: $document_id})
RETURN d.processing_status AS processing_status,
       d.error AS error,
       d.failed_stage AS failed_stage
"""


async def _read_status(session: Any, document_id: str) -> dict[str, Any] | None:
    """Query the Document node and return its status fields, or None if absent.

    Args:
        session: Open Neo4j AsyncSession.
        document_id: 64-char SHA-256 hex — used as a bound Cypher $param (T-07-09).

    Returns:
        dict with keys processing_status, error, failed_stage — or None if not found.
    """
    result = await session.run(_READ_STATUS_CYPHER, document_id=document_id)
    record = await result.single()
    if record is None:
        return None
    return {
        "processing_status": record["processing_status"],
        "error": record["error"],
        "failed_stage": record["failed_stage"],
    }


# ---------------------------------------------------------------------------
# POST /documents — upload, save, MERGE queued, enqueue (API-01, D-04)
# ---------------------------------------------------------------------------


@router.post("/documents", status_code=202)
async def create_document(
    request: Request,
    file: UploadFile = File(...),
    db: GraphDB = Depends(get_db),
    settings: Any = Depends(get_settings),
) -> JSONResponse:
    """Accept a PDF, compute its SHA-256 id, save to disk, MERGE queued node, enqueue.

    Returns:
        202 JSON {document_id: str, task_id: str}  — brand-new upload
        202 JSON {document_id: str, task_id: null}  — already queued/processing (D-05)
        200 JSON {document_id: str, task_id: null}  — already written (D-05)

    Raises:
        415: filename does not end in .pdf or wrong content-type (T-07-08)
        413: file exceeds MAX_UPLOAD_BYTES (T-07-06)
        400: file is empty
        503: Neo4j is unavailable
    """
    # --- T-07-08: validate filename suffix and content-type ---
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only .pdf files are accepted",
        )
    content_type = (file.content_type or "").split(";")[0].strip()
    if content_type not in _ACCEPTED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content-type: {content_type}",
        )

    # --- Read bytes + size/empty validation ---
    data = await file.read()
    if len(data) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum allowed size of {MAX_UPLOAD_BYTES} bytes",
        )

    # --- Compute deterministic document_id (same formula as PdfParser — idempotent) ---
    document_id = hashlib.sha256(data).hexdigest()

    # --- T-07-03: guard before ANY Neo4j or Celery operation ---
    if not db.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j unavailable — cannot process upload",
        )

    # --- D-05 dedup check: read current node status BEFORE writing/enqueuing ---
    async with db.session() as s:
        existing = await _read_status(s, document_id)

        if existing is not None:
            current_status = existing["processing_status"]

            # D-05: already written — no re-LLM
            if current_status == STATUS_WRITTEN:
                logger.info(
                    "documents: skip re-enqueue (written) doc_id={}", document_id
                )
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={"document_id": document_id, "task_id": None},
                )

            # D-05: in-flight — no duplicate enqueue
            if current_status in (STATUS_QUEUED, STATUS_PROCESSING):
                logger.info(
                    "documents: skip re-enqueue ({}) doc_id={}", current_status, document_id
                )
                return JSONResponse(
                    status_code=status.HTTP_202_ACCEPTED,
                    content={"document_id": document_id, "task_id": None},
                )

            # D-05/D-06: previously failed — re-enqueue but reset stale error/failed_stage first
            if current_status == STATUS_FAILED:
                logger.info(
                    "documents: re-enqueue after failure doc_id={}", document_id
                )
                # T-07-07: sanitize filename before any disk write
                safe_name = Path(filename).name
                doc_dir = Path(settings.storage_root) / "documents" / document_id
                doc_dir.mkdir(parents=True, exist_ok=True)
                (doc_dir / safe_name).write_bytes(data)

                # D-06 freshness: reset_for_requeue clears error + failed_stage
                await reset_for_requeue(s, document_id)
                task = process_document.delay(document_id)
                return JSONResponse(
                    status_code=status.HTTP_202_ACCEPTED,
                    content={"document_id": document_id, "task_id": task.id},
                )

        # --- Brand-new document: save file, MERGE queued, enqueue (D-04 ordering) ---
        # T-07-07: Path(filename).name sanitizes against path traversal
        safe_name = Path(filename).name
        doc_dir = Path(settings.storage_root) / "documents" / document_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        (doc_dir / safe_name).write_bytes(data)

        file_uri = f"documents/{document_id}/{safe_name}"

        # D-04: MERGE queued node BEFORE enqueue (no 404 race if task picks it up fast)
        await merge_document_queued(s, document_id, file_uri)

    # Enqueue AFTER the session is closed (Celery outside Neo4j session)
    task = process_document.delay(document_id)
    logger.info(
        "documents: enqueued doc_id={} task_id={}", document_id, task.id
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"document_id": document_id, "task_id": task.id},
    )


# ---------------------------------------------------------------------------
# GET /documents/{document_id} — status poll (API-02, D-06)
# ---------------------------------------------------------------------------


@router.get("/documents/{document_id}")
async def get_document(
    document_id: str,
    db: GraphDB = Depends(get_db),
) -> dict[str, Any]:
    """Return Document node status fields or 404 if not found.

    Returns:
        200 JSON {document_id, processing_status, error, failed_stage}

    Raises:
        503: Neo4j unavailable
        404: no Document node with that id
    """
    if not db.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j unavailable",
        )

    async with db.session() as s:
        row = await _read_status(s, document_id)

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="document not found",
        )

    return {"document_id": document_id, **row}
