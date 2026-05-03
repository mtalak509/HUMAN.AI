from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from loguru import logger

from core.config import Settings, get_settings as _get_settings
from core.graph import GraphDB
from core.logger import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    try:
        await db.connect_with_retry(retries=3, delays=[1, 3, 9])
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
    return request.app.state.settings


def get_db(request: Request) -> GraphDB:
    return request.app.state.db


@app.get("/health")
async def health(db: GraphDB = Depends(get_db)) -> dict:
    if db is None or not db.is_connected:
        return {"status": "degraded", "neo4j": "unavailable"}

    try:
        await db.ping()
        return {"status": "ok"}
    except Exception:
        return {"status": "degraded", "neo4j": "unavailable"}
