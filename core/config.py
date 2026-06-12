from functools import lru_cache
from pathlib import Path

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

    # Document storage
    storage_root: Path = Field(
        default=Path("storage"),
        description="Root directory for document storage (relative to cwd or absolute)",
    )

    # R&D / external LLM (optional — used by rnd/ scripts only)
    openrouter_api_key: str | None = Field(
        default=None,
        description="OpenRouter API key for R&D LLM scripts; env OPENROUTER_API_KEY",
    )

    # LLM extractor config (Phase 5)
    extractor_model: str = Field(
        default="qwen/qwen3.6-plus",
        description="OpenRouter model id for the LLM extractor; env EXTRACTOR_MODEL",
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API base URL; env OPENROUTER_BASE_URL",
    )
    extractor_timeout: float = Field(
        default=60.0,
        description="LLM call timeout in seconds; env EXTRACTOR_TIMEOUT",
    )
    extractor_temperature: float = Field(
        default=0.0,
        description="LLM sampling temperature; env EXTRACTOR_TEMPERATURE",
    )

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
    return Settings()  # type: ignore[call-arg]  # env/.env supply required secrets at runtime
