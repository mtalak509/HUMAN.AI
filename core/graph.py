import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from loguru import logger
from neo4j import AsyncDriver, AsyncGraphDatabase, AsyncSession


class GraphDB:
    """
    Async Neo4j driver wrapper.

    Предоставляет:
    - ping(): проверка связи с Neo4j (RETURN 1)
    - session(): async context manager для выполнения запросов
    - connect_with_retry(): startup с graceful degradation
    - close(): корректное закрытие driver
    """

    def __init__(self, uri: str, user: str, password: str) -> None:
        self._uri = uri
        self._user = user
        self._password = password
        self._driver: AsyncDriver | None = None
        self.is_connected: bool = False

    async def connect_with_retry(
        self,
        retries: int = 3,
        delays: list[int] | None = None,
    ) -> None:
        """
        Инициализирует async driver и проверяет связь с Neo4j.
        После исчерпания попыток: is_connected=False, не raise.
        """
        if delays is None:
            delays = [1, 3, 9]

        self._driver = AsyncGraphDatabase.driver(
            self._uri,
            auth=(self._user, self._password),
        )

        for attempt in range(1, retries + 1):
            try:
                await self.ping()
                self.is_connected = True
                logger.info("Neo4j connected on attempt {}/{}", attempt, retries)
                return
            except Exception as exc:
                logger.warning("Neo4j ping failed (attempt {}/{}): {}", attempt, retries, exc)
                if attempt < retries:
                    delay = delays[attempt - 1] if attempt - 1 < len(delays) else delays[-1]
                    logger.info("Retrying in {}s...", delay)
                    await asyncio.sleep(delay)

        logger.error(
            "Neo4j unavailable after {} attempts - running in degraded mode",
            retries,
        )
        self.is_connected = False

    async def ping(self) -> None:
        """
        Проверяет связь: выполняет RETURN 1.
        Raise если driver не инициализирован или Neo4j недоступен.
        """
        if self._driver is None:
            raise RuntimeError("GraphDB driver not initialized - call connect_with_retry first")

        async with self._driver.session() as session:
            result = await session.run("RETURN 1")
            await result.consume()

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Async context manager для сессий: async with db.session() as s.
        Raise если is_connected=False.
        """
        if self._driver is None or not self.is_connected:
            raise RuntimeError("Neo4j is not connected - cannot create session")

        async with self._driver.session() as neo4j_session:
            yield neo4j_session

    async def close(self) -> None:
        """Корректно закрывает async driver. Вызывается в lifespan shutdown."""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
            self.is_connected = False
            logger.info("Neo4j driver closed")
