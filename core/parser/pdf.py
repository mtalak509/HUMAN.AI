"""PdfParser — async PDF extraction + file storage layer.

Responsibilities (plan 04-01):
  - Compute deterministic SHA-256 document_id from PDF bytes (Pattern 2)
  - Offload sync pypdf extraction to thread pool via run_in_executor (Pattern 3, Pitfall 3)
  - Persist original PDF + extracted text.md under {storage_root}/documents/{id}/ (Pattern 4)
  - Return a frozen ParseResult dataclass (Pattern 7)

NOT in this plan:
  - Document-node MERGE in Neo4j — added in plan 04-02 (see comment below)
"""

import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from core.config import get_settings
from core.parser._backend import PyPdfBackend, TextExtractorBackend


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
      - db: GraphDB | None — for plan 04-02 Document-node MERGE; None is safe here
      - storage_root: override get_settings().storage_root (useful in tests with tmp_path)
      - backend: override PyPdfBackend (extensibility seam D-02)

    Usage:
        parser = PdfParser(db=None, storage_root=tmp_path)
        result = await parser.parse(Path("resume.pdf"))
    """

    def __init__(
        self,
        db: object | None = None,
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
            Document-node MERGE added in plan 04-02.
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

        result = ParseResult(
            document_id=document_id,
            extracted_text=text,
            file_uri=file_uri,
            text_uri=text_uri,
            extraction_status=status,
            parser_version=parser_version,
        )

        # Document-node MERGE added in plan 04-02
        # if self._db is not None and hasattr(self._db, "is_connected"):
        #     if not self._db.is_connected:
        #         logger.warning("Neo4j unavailable — node not persisted id={}", document_id)
        #     else:
        #         async with self._db.session() as session:
        #             await session.run(MERGE_DOCUMENT_CYPHER, ...)

        return result
