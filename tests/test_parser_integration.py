"""Integration tests for core.parser — PARSE-03 and corpus smoke.

These tests require a running Neo4j instance and are deferred to plan 04-02.
All test functions here are stubbed with @pytest.mark.skip so the suite stays
green in plan 04-01 (Wave 1 / pre-Neo4j write).

Implemented in: plan 04-02 (Wave 2 — Document-node MERGE)
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.mark.skip(reason="implemented in plan 04-02")
async def test_document_node_created(tmp_path: Path) -> None:
    """After parse(), a :Document node with the correct id exists in Neo4j."""
    ...


@pytest.mark.skip(reason="implemented in plan 04-02")
async def test_document_node_idempotent(tmp_path: Path) -> None:
    """Parsing the same PDF twice does not create duplicate :Document nodes."""
    ...


@pytest.mark.skip(reason="implemented in plan 04-02")
async def test_document_node_fields(tmp_path: Path) -> None:
    """The :Document node has file_uri, text_uri, parser_version, extraction_status, ingested_at set."""
    ...


@pytest.mark.skip(reason="implemented in plan 04-02")
async def test_rnd_corpus_smoke(tmp_path: Path) -> None:
    """All PDFs under rnd/data/resume/ parse without raising and produce status 'ok'."""
    ...
