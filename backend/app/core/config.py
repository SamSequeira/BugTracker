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


# ---------------------------------------------------------------------------
# AWS / S3
# ---------------------------------------------------------------------------

class S3Config:
    """All S3-related settings resolved from environment variables."""

    @property
    def bucket_name(self) -> str:
        return _require("S3_BUCKET_NAME")

    @property
    def region(self) -> str:
        return _require("AWS_REGION")

    @property
    def access_key_id(self) -> str:
        """
        AWS_ACCESS_KEY_ID — optional when running on EC2/ECS/Lambda with an
        IAM role attached; required for local development.
        """
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
        """
        S3 upload is enabled when S3_BUCKET_NAME and AWS_REGION are set.
        Set S3_ENABLED=false to disable S3 uploads in local dev without
        unsetting the other vars.
        """
        flag = _optional("S3_ENABLED", "true").lower()
        if flag in ("false", "0", "no"):
            return False
        return bool(_optional("S3_BUCKET_NAME") and _optional("AWS_REGION"))


s3_config = S3Config()
