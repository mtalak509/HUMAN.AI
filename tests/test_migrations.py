from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio

from core.config import Settings
from core.database.graph import GraphDB
from core.database.migrations import CONSTRAINTS, INDEXES, MigrationManager

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def graph_db(settings: Settings) -> AsyncGenerator[GraphDB, None]:
    db = GraphDB(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
    )
    await db.connect_with_retry(retries=1, delays=[0])
    yield db
    await db.close()


async def _show_constraint_names(db: GraphDB) -> set[str]:
    async with db.session() as session:
        result = await session.run("SHOW CONSTRAINTS YIELD name")
        records = [record async for record in result]
    return {r["name"] for r in records}


async def test_apply_all_smoke(graph_db: GraphDB) -> None:
    await MigrationManager(graph_db).apply_all()

    names = await _show_constraint_names(graph_db)
    assert "candidate_id_unique" in names
    assert "institution_name_unique" in names


async def test_apply_all_idempotent(graph_db: GraphDB) -> None:
    await MigrationManager(graph_db).apply_all()
    names_after_first = await _show_constraint_names(graph_db)

    await MigrationManager(graph_db).apply_all()
    names_after_second = await _show_constraint_names(graph_db)

    assert names_after_first == names_after_second
    expected = {name for name, _ in CONSTRAINTS}
    assert expected.issubset(names_after_second)


async def test_apply_all_degraded_is_noop(settings: Settings) -> None:
    db = GraphDB(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
    )
    assert db.is_connected is False

    await MigrationManager(db).apply_all()

    assert db.is_connected is False
    assert len(CONSTRAINTS) == 11  # 12 − Fact − Role + Institution (refactor 2026-06-21)
    assert len(INDEXES) == 3  # 5 − fact_predicate_idx − fact_is_current_idx (refactor 2026-06-21)
