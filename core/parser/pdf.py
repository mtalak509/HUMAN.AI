"""PdfParser — async PDF extraction + file storage layer.

Responsibilities (plan 04-01):
  - Compute deterministic SHA-256 document_id from PDF bytes (Pattern 2)
  - Offload sync pypdf extraction to thread pool via run_in_executor (Pattern 3, Pitfall 3)
  - Persist original PDF + extracted text.md under {storage_root}/documents/{id}/ (Pattern 4)
  - Return a frozen ParseResult dataclass (Pattern 7)

Responsibilities (plan 04-02):
  - MERGE Document node into Neo4j keyed on document_id (PARSE-03, D-09)
  - Graceful degradation: if Neo4j is unavailable, files are saved and ParseResult is returned
    without crashing (T-04-06)
"""

import asyncio
import datetime as dt
import hashlib
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from core.config import get_settings
from core.database.graph import GraphDB
from core.parser._backend import PyPdfBackend, TextExtractorBackend

# Cypher MERGE for Document node (PARSE-03, T-04-05 — bound parameters, no string interpolation)
# MERGE on .id only (document_id_unique constraint — do not change the key).
# Uses SET (not ON-CREATE-SET) — re-parsing the same PDF refreshes fields idempotently (WRITE-04).
MERGE_DOCUMENT_CYPHER = """
MERGE (d:Document {id: $document_id})
SET d.type = $type,
    d.file_uri = $file_uri,
    d.text_uri = $text_uri,
    d.parser_version = $parser_version,
    d.extraction_status = $extraction_status,
    d.ingested_at = $ingested_at
RETURN d
"""


@dataclass(frozen=True)
class ParseResult:
    """Immutable result of a PDF parse operation.

    Fields align with the Document node schema (plan 04-02 adds the MERGE).
    URIs are relative to storage_root (A2).
    """

    document_id: str         # SHA-256 hex (64 chars) of raw PDF bytes
    extracted_text: str      # full text with --- PAGE i --- markers
    file_uri: str            # relative: documents/{id}/{filename}
    text_uri: str            # relative: documents/{id}/text.md
    extraction_status: str   # "ok" | "empty"  (D-08)
    parser_version: str      # e.g. "pypdf-v1"


class PdfParser:
    """Async PDF parsing + storage service.

    Constructor is dependency-injectable:
      - db: GraphDB | None — for Document-node MERGE; None is safe (degraded mode)
      - storage_root: override get_settings().storage_root (useful in tests with tmp_path)
      - backend: override PyPdfBackend (extensibility seam D-02)

    Usage:
        parser = PdfParser(db=None, storage_root=tmp_path)
        result = await parser.parse(Path("resume.pdf"))
    """

    def __init__(
        self,
        db: GraphDB | None = None,
        storage_root: Path | None = None,
        backend: TextExtractorBackend | None = None,
    ) -> None:
        self._db = db
        self._storage_root = storage_root or get_settings().storage_root
        self._backend = backend or PyPdfBackend()

    @staticmethod
    def _compute_document_id(pdf_bytes: bytes) -> str:
        """Compute a deterministic 64-char SHA-256 hex id from raw PDF bytes.

        Idempotent: same bytes always yield the same id (Pattern 2).
        Directory-safe: hex chars 0-9a-f only (T-04-03 — no traversal possible).
        """
        return hashlib.sha256(pdf_bytes).hexdigest()

    async def parse(self, pdf_path: Path) -> ParseResult:
        """Extract text from a PDF, persist files to storage, return ParseResult.

        Args:
            pdf_path: Path to the PDF file (must exist, must have .pdf suffix).

        Returns:
            ParseResult with document_id, extracted_text, file_uri, text_uri,
            extraction_status ("ok"|"empty"), parser_version.

        Raises:
            FileNotFoundError: if pdf_path does not exist.
            ValueError: if pdf_path does not have a .pdf suffix.

        Note:
            If Neo4j is unavailable (db=None or db.is_connected=False), the Document
            node is NOT persisted but parse() still returns a complete ParseResult
            (graceful degradation per CLAUDE.md / T-04-06).
        """
        # --- Input validation (V5 / Security T-04-01) ---
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        if pdf_path.suffix.lower() != ".pdf":
            raise ValueError(f"Expected a .pdf file, got: {pdf_path.name}")

        # --- Read bytes + compute deterministic id (Pattern 2) ---
        pdf_bytes = pdf_path.read_bytes()
        document_id = self._compute_document_id(pdf_bytes)

        # --- Offload sync pypdf extraction to thread pool (Pattern 3, Pitfall 3) ---
        loop = asyncio.get_running_loop()
        text, status = await loop.run_in_executor(
            None,
            self._backend.extract,
            pdf_path,
        )

        # --- Storage writes (Pattern 4) ---
        # Sanitize filename against path traversal (Security T-04-02)
        safe_name = Path(pdf_path.name).name

        doc_dir = self._storage_root / "documents" / document_id
        doc_dir.mkdir(parents=True, exist_ok=True)

        # Write original PDF bytes
        (doc_dir / safe_name).write_bytes(pdf_bytes)

        # Write extracted text as .md (D-04 / D-06)
        (doc_dir / "text.md").write_text(text, encoding="utf-8")

        # --- Build relative URIs (A2 — relative, not absolute) ---
        file_uri = f"documents/{document_id}/{safe_name}"
        text_uri = f"documents/{document_id}/text.md"

        # --- Resolve parser version from backend (fallback for custom backends) ---
        parser_version = getattr(self._backend, "PARSER_VERSION", "pypdf-v1")

        logger.info(
            "pdf_parser: parsed file={} id={} chars={} status={}",
            safe_name,
            document_id,
            len(text),
            status,
        )

        # --- Document-node MERGE (PARSE-03, plan 04-02) ---
        # Files are already on disk at this point; a Neo4j outage never loses data.
        # Guard on is_connected BEFORE calling session() — session() raises RuntimeError
        # when not connected (Pitfall 4 / T-04-06 graceful degradation).
        if self._db is None or not self._db.is_connected:
            logger.warning(
                "pdf_parser: Neo4j unavailable — document node not persisted id={}",
                document_id,
            )
        else:
            async with self._db.session() as session:
                await session.run(
                    MERGE_DOCUMENT_CYPHER,
                    document_id=document_id,
                    type="resume",
                    file_uri=file_uri,
                    text_uri=text_uri,
                    parser_version=parser_version,
                    extraction_status=status,
                    ingested_at=dt.datetime.now(dt.UTC).isoformat(),
                )
            logger.info("pdf_parser: document node merged id={}", document_id)

        return ParseResult(
            document_id=document_id,
            extracted_text=text,
            file_uri=file_uri,
            text_uri=text_uri,
            extraction_status=status,
            parser_version=parser_version,
        )
