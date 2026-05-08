import logging
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # ── Application ───────────────────────────────────────────────────────────
    APP_NAME: str = "reko-ai-recommendation-system"
    DEBUG: bool = True

    # ── Database (MongoDB via Motor + Beanie) ─────────────────────────────────
    DATABASE_URL: str = Field(
        default="mongodb://localhost:27017",
        description="MongoDB connection URI"
    )
    DATABASE_NAME: str = "reko_ai_system_db"

    # ── Auth — RS256 JWT Verification ─────────────────────────────────────────
    # JWKS_URL: the /.well-known/jwks.json endpoint on reko-ai-auth-system
    JWKS_URL: str = "http://localhost:8000/api/v1/.well-known/jwks.json"
    JWT_ALGORITHM: str = "RS256"
    # JWT_PUBLIC_KEY: RS256 public key in PEM format (set in env or provide file)
    JWT_PUBLIC_KEY: str = ""
    JWT_PUBLIC_KEY_PATH: str = "app/certs/public.pem"
    # INTERNAL_SERVICE_SECRET: shared secret for service-to-service calls
    INTERNAL_SERVICE_SECRET: str = ""

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
