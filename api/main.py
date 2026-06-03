from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import Depends, FastAPI, Request, Response, status
from loguru import logger

from core.config import Settings
from core.config import get_settings as _get_settings
from core.database.graph import GraphDB
from core.database.migrations import MigrationManager
from core.logger import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = _get_settings()
    app.state.settings = settings

    setup_logging(level=settings.log_level, json_mode=settings.log_json)
    logger.info(
        "Logging configured: level={} json={}",
        settings.log_level,
        settings.log_json,
    )

    db = GraphDB(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
    )
    migrations_manager = MigrationManager(db)
    try:
        await db.connect_with_retry(retries=3, delays=[1, 3, 9])
        if db.is_connected:
            await migrations_manager.apply_all()
    except Exception as exc:
        logger.warning("Neo4j unavailable during startup: {}", exc)
        if not hasattr(db, "is_connected"):
            db.is_connected = False
    app.state.db = db
    logger.info("Application startup complete")

    try:
        yield
    finally:
        try:
            await db.close()
        except Exception as exc:
            logger.warning("GraphDB close failed: {}", exc)
        logger.info("Application shutdown complete")


app = FastAPI(title="HUMAN.AI", version="0.1.0", lifespan=lifespan)


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_db(request: Request) -> GraphDB:
    return cast(GraphDB, request.app.state.db)


@app.get("/health")
async def health(
    response: Response,
    db: GraphDB = Depends(get_db),
) -> dict[str, str]:
    if db is None or not db.is_connected:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "neo4j": "unavailable"}

    try:
        await db.ping()
        return {"status": "ok"}
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "neo4j": "unavailable"}
