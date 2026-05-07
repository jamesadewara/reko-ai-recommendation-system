import logging
from typing import List, Optional
from pydantic import computed_field, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    # ── Application ───────────────────────────────────────────────────────────
    APP_NAME: str = "reco-ai-auth-system"
    DEBUG: bool = True

    # ── Database (MongoDB async via Beanie and Pymongo) ──────────────────────────────
    DATABASE_URL: str = Field(
        default="mongodb://localhost:27017/reko_ai_system_db",
        description="Main database connection string"
    )

    # ── Auth — RS256 JWT Verification via luxe-auth ───────────────────────────
    JWKS_URL: str = "http://localhost:8000/api/v1/.well-known/jwks.json"
    JWT_ALGORITHM: str = "RS256"
    JWT_PUBLIC_KEY: str = ""
    INTERNAL_SERVICE_SECRET: str = ""

    # ── Database Pooling (Optimized for production) ──────────────────────────
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE: int = 3600  # 1 hour
    DB_POOL_PRE_PING: bool = True
    DB_CONNECT_TIMEOUT: int = 60 # 1 minute for self-healing

    @computed_field
    @property
    def ASYNC_DATABASE_URL(self) -> str:
        """Standardizes DATABASE_URL to use the asyncpg driver for PostgreSQL."""
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    # ── Service Mesh URLs ─────────────────────────────────────────────────────
    REKO_AI_AUTH_URL: str = "http://localhost:8000"
    REKO_AI_SYSTEM_URL: str = "http://localhost:8001"
    REKO_AI_FRONTEND_URL: str = "http://localhost:3000"

    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ALLOWED_ORIGINS: str = (
        "http://localhost:3000,http://localhost:8000,"
        "http://localhost:8001"
    )

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore",
        case_sensitive=True
    )

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]


settings = Settings()
