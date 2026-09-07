"""
app/core/config.py
------------------
Central configuration — reads from environment variables.

Copy backend/.env.example to backend/.env and fill in your values.
The app loads .env automatically via python-dotenv (if installed),
or you can export the variables in your shell before starting uvicorn.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Load .env if python-dotenv is available
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(_env_path)
except ImportError:
    pass  # python-dotenv is optional; env vars can be set externally


def _require(name: str) -> str:
    """Return the value of an env var or raise a clear error."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}\n"
            f"Set it in backend/.env or export it before starting the server."
        )
    return value


def _optional(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


AWS_REGION = _optional("AWS_REGION", "us-east-1")
S3_BUCKET_NAME = _optional("S3_BUCKET_NAME", "bugtracker-repositories")


# ---------------------------------------------------------------------------
# AWS / S3
# ---------------------------------------------------------------------------

class S3Config:
    """All S3-related settings resolved from environment variables."""

    @property
    def bucket_name(self) -> str:
        return _optional("S3_BUCKET_NAME", "bugtracker-repositories")

    @property
    def region(self) -> str:
        return _optional("AWS_REGION", "us-east-1")

    @property
    def access_key_id(self) -> str:
        return _optional("AWS_ACCESS_KEY_ID")

    @property
    def secret_access_key(self) -> str:
        return _optional("AWS_SECRET_ACCESS_KEY")

    @property
    def prefix(self) -> str:
        """S3 key prefix for all uploaded repositories."""
        return _optional("S3_PREFIX", "repositories")

    @property
    def presigned_expiry_seconds(self) -> int:
        """How long pre-signed download URLs remain valid."""
        return int(_optional("S3_PRESIGNED_EXPIRY", "3600"))

    @property
    def enabled(self) -> bool:
        flag = _optional("S3_ENABLED", "true").lower()
        if flag in ("false", "0", "no"):
            return False
        return bool(_optional("S3_BUCKET_NAME") and _optional("AWS_REGION"))


class Settings:
    @property
    def DATABASE_URL(self) -> str:
        """Database URL suitable for SQLAlchemy's async engine."""
        url = _require("DATABASE_URL")
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("sqlite://"):
            return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return url

    @property
    def JWT_SECRET_KEY(self) -> str:
        return _optional("JWT_SECRET_KEY", "dev-secret-key-1234567890-change-in-prod")

    @property
    def JWT_ALGORITHM(self) -> str:
        return _optional("JWT_ALGORITHM", "HS256")

    @property
    def ACCESS_TOKEN_EXPIRE_MINUTES(self) -> int:
        return int(
            _optional(
                "ACCESS_TOKEN_EXPIRE_MINUTES",
                "60"
            )
        )

    @property
    def CORS_ORIGINS(self) -> list[str]:
        return [
            origin.strip()
            for origin in _optional(
                "CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000",
            ).split(",")
            if origin.strip()
        ]


settings = Settings()
s3_config = S3Config()
