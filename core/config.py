from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Конфигурация приложения. Читается из .env (или переменных окружения).
    Все поля обязательны к заданию (пустых значений нет) кроме neo4j_password.
    """

    # Graph DB (per D-07)
    neo4j_uri: str = Field(default="bolt://localhost:7687", description="Neo4j Bolt URI")
    neo4j_user: str = Field(default="neo4j", description="Neo4j username")
    neo4j_password: str = Field(description="Neo4j password — обязательно в .env")

    # Vector store
    qdrant_url: str = Field(default="http://localhost:6333", description="Qdrant REST URL")
    redis_url: str = Field(default="redis://localhost:6379", description="Redis connection URL")

    # logging
    log_level: str = Field(
        default="INFO",
        description="Loguru log level: TRACE/DEBUG/INFO/WARNING/ERROR",
    )
    log_json: bool = Field(default=False, description="LOG_JSON=true -> serialize=True in loguru")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    """
    Возвращает кэшированный экземпляр Settings (per D-08).
    Кэш сбрасывается через get_settings.cache_clear() в тестах.
    """
    return Settings()
