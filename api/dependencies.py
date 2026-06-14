"""api.dependencies — Shared FastAPI dependency injection helpers.

These helpers read from app.state (populated in lifespan). Having them in a
separate module breaks the circular-import that would arise if routers imported
from api.main while api.main imports the routers.

Usage in routers:
    from api.dependencies import get_db, get_settings

Usage in tests:
    from api.dependencies import get_db, get_settings
    app.dependency_overrides[get_db] = lambda: FakeGraphDB()
    app.dependency_overrides[get_settings] = lambda: FakeSettings()
"""

from typing import cast

from fastapi import Request

from core.config import Settings
from core.database.graph import GraphDB


def get_settings(request: Request) -> Settings:
    """Inject Settings from app.state (populated in lifespan)."""
    return cast(Settings, request.app.state.settings)


def get_db(request: Request) -> GraphDB:
    """Inject GraphDB from app.state (populated in lifespan)."""
    return cast(GraphDB, request.app.state.db)
