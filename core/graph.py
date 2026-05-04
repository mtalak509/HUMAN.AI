"""Re-export of GraphDB for callers that use the legacy ``core.graph`` import path."""

from core.database.graph import GraphDB

__all__ = ["GraphDB"]
