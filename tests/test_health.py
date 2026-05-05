from typing import cast

from api.main import health
from core.database.graph import GraphDB


class DummyDB:
    def __init__(self, is_connected: bool, should_fail: bool = False) -> None:
        self.is_connected = is_connected
        self._should_fail = should_fail

    async def ping(self) -> None:
        if self._should_fail:
            raise RuntimeError("ping failed")


async def test_health_ok_when_ping_succeeds() -> None:
    db = DummyDB(is_connected=True, should_fail=False)

    result = await health(db=cast(GraphDB, db))

    assert result == {"status": "ok"}


async def test_health_degraded_when_db_disconnected() -> None:
    db = DummyDB(is_connected=False, should_fail=False)

    result = await health(db=cast(GraphDB, db))

    assert result == {"status": "degraded", "neo4j": "unavailable"}


async def test_health_degraded_when_ping_fails() -> None:
    db = DummyDB(is_connected=True, should_fail=True)

    result = await health(db=cast(GraphDB, db))

    assert result == {"status": "degraded", "neo4j": "unavailable"}
