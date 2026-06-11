"""Integration tests for core.parser — PARSE-03 and corpus smoke.

Tests require a running Neo4j instance. When Neo4j is unavailable (graph_db.is_connected=False),
Neo4j-dependent tests skip cleanly. The corpus smoke test (test_rnd_corpus_smoke) runs
with db=None so it validates extraction across all resumes regardless of infra.

Implemented in plan 04-02 (Wave 2 — Document-node MERGE).
"""

from pathlib import Path

import pytest

from core.database.graph import GraphDB
from core.parser.pdf import PdfParser

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_document_node_created(graph_db: GraphDB, tmp_path: Path) -> None:
    """After parse(), a :Document node with the correct id exists in Neo4j."""
    if not graph_db.is_connected:
        pytest.skip("Neo4j unavailable")

    pdf = next(Path("rnd/data/resume").glob("*.pdf"))
    parser = PdfParser(db=graph_db, storage_root=tmp_path)
    result = await parser.parse(pdf)

    async with graph_db.session() as session:
        r = await session.run("MATCH (d:Document {id: $id}) RETURN d", id=result.document_id)
        record = await r.single()

    assert record is not None, f"Document node not found for id={result.document_id}"


async def test_document_node_idempotent(graph_db: GraphDB, tmp_path: Path) -> None:
    """Parsing the same PDF twice does not create duplicate :Document nodes."""
    if not graph_db.is_connected:
        pytest.skip("Neo4j unavailable")

    pdf = next(Path("rnd/data/resume").glob("*.pdf"))
    parser = PdfParser(db=graph_db, storage_root=tmp_path)

    result1 = await parser.parse(pdf)
    result2 = await parser.parse(pdf)

    assert result1.document_id == result2.document_id, "document_id must be deterministic (SHA-256)"

    async with graph_db.session() as session:
        r = await session.run(
            "MATCH (d:Document {id: $id}) RETURN count(d) AS c",
            id=result1.document_id,
        )
        record = await r.single()

    assert record is not None
    assert record["c"] == 1, f"Expected 1 Document node, got {record['c']} (MERGE must be idempotent)"


async def test_document_node_fields(graph_db: GraphDB, tmp_path: Path) -> None:
    """The :Document node has file_uri, text_uri, parser_version, extraction_status set."""
    if not graph_db.is_connected:
        pytest.skip("Neo4j unavailable")

    pdf = next(Path("rnd/data/resume").glob("*.pdf"))
    parser = PdfParser(db=graph_db, storage_root=tmp_path)
    result = await parser.parse(pdf)

    async with graph_db.session() as session:
        r = await session.run("MATCH (d:Document {id: $id}) RETURN d", id=result.document_id)
        record = await r.single()

    assert record is not None
    node = record["d"]

    # D-09 fields must be non-null and correct
    assert node["text_uri"] is not None, "text_uri must be set on Document node"
    assert node["parser_version"] == "pypdf-v1", f"parser_version mismatch: {node['parser_version']}"
    assert node["extraction_status"] in {"ok", "empty"}, (
        f"extraction_status must be 'ok' or 'empty', got: {node['extraction_status']}"
    )
    assert node["file_uri"] is not None, "file_uri must be set on Document node"
    assert node["ingested_at"] is not None, "ingested_at must be set on Document node"


async def test_rnd_corpus_smoke(tmp_path: Path) -> None:
    """All PDFs under rnd/data/resume/ parse without raising; status='ok' implies non-empty text.

    Runs with db=None so it validates extraction across all resumes regardless of infra.
    """
    resume_dir = Path("rnd/data/resume")
    if not resume_dir.exists():
        pytest.skip("rnd/data/resume directory not found")

    pdf_files = list(resume_dir.glob("*.pdf"))
    if not pdf_files:
        pytest.skip("No PDF files found in rnd/data/resume/")

    parser = PdfParser(db=None, storage_root=tmp_path)

    for pdf in pdf_files:
        result = await parser.parse(pdf)
        assert result.document_id, f"document_id must be non-empty for {pdf.name}"
        assert result.extraction_status in {"ok", "empty"}, (
            f"Unexpected extraction_status={result.extraction_status} for {pdf.name}"
        )
        if result.extraction_status == "ok":
            assert len(result.extracted_text) > 0, (
                f"extracted_text must be non-empty when status='ok' for {pdf.name}"
            )
