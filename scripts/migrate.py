"""
Идемпотентная миграция схемы Neo4j (CLI-обёртка над MigrationManager).

Запуск: python scripts/migrate.py

Источник истины для constraints/indexes — core.database.migrations.
Безопасен для повторного запуска (IF NOT EXISTS).
"""

import asyncio
import sys

from loguru import logger

from core.config import get_settings
from core.database.graph import GraphDB
from core.database.migrations import MigrationManager


async def main() -> None:
    settings = get_settings()
    db = GraphDB(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
    )

    try:
        await db.connect_with_retry()
        if not db.is_connected:
            logger.error("Neo4j unavailable — migration aborted")
            sys.exit(1)

        try:
            await MigrationManager(db).apply_all()
        except Exception as exc:
            logger.error("Migration failed: {}", exc)
            sys.exit(1)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
