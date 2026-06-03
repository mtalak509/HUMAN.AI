from typing import cast

from fastapi import Response, status

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
    response = Response()

    result = await health(response=response, db=cast(GraphDB, db))

    assert result == {"status": "ok"}
    assert response.status_code == status.HTTP_200_OK


async def test_health_degraded_when_db_disconnected() -> None:
    db = DummyDB(is_connected=False, should_fail=False)
    response = Response()

    result = await health(response=response, db=cast(GraphDB, db))

    assert result == {"status": "degraded", "neo4j": "unavailable"}
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


async def test_health_degraded_when_ping_fails() -> None:
    db = DummyDB(is_connected=True, should_fail=True)
    response = Response()

    result = await health(response=response, db=cast(GraphDB, db))

    assert result == {"status": "degraded", "neo4j": "unavailable"}
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
