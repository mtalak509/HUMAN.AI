import redis.asyncio as aioredis
from neo4j import AsyncDriver
from qdrant_client import QdrantClient

from core.config import Settings


async def test_neo4j_ping(neo4j_driver: AsyncDriver) -> None:
    async with neo4j_driver.session() as session:
        result = await session.run("RETURN 1 AS n")
        record = await result.single()
    assert record is not None
    assert record["n"] == 1


def test_qdrant_health(qdrant_client: QdrantClient) -> None:
    collections = qdrant_client.get_collections()
    assert collections is not None


async def test_redis_ping(settings: Settings) -> None:
    r = aioredis.from_url(str(settings.redis_url))
    try:
        pong = await r.ping()
    finally:
        await r.aclose()
    assert pong is True
