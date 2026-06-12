from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from qdrant_client import QdrantClient

from core.config import Settings, get_settings
from core.database.graph import GraphDB
from neo4j import AsyncDriver, AsyncGraphDatabase


@pytest.fixture(scope="session")
def settings() -> Settings:
    return get_settings()


@pytest_asyncio.fixture(scope="session")
async def neo4j_driver(settings: Settings) -> AsyncGenerator[AsyncDriver, None]:
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    yield driver
    try:
        await driver.close()
    except Exception:
        pass  # Windows ProactorEventLoop: _proactor can be None on teardown


@pytest.fixture(scope="session")
def qdrant_client(settings: Settings) -> Generator[QdrantClient, None, None]:
    client = QdrantClient(url=str(settings.qdrant_url))
    yield client
    client.close()


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def graph_db(settings: Settings) -> AsyncGenerator[GraphDB, None]:
    db = GraphDB(uri=settings.neo4j_uri, user=settings.neo4j_user, password=settings.neo4j_password)
    await db.connect_with_retry(retries=1, delays=[0])
    yield db
    await db.close()
