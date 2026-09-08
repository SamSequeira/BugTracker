"""
app/services/s3_service.py
--------------------------
Thin wrapper around boto3 for uploading repository ZIPs to S3.

All configuration is read from app.core.config.S3Config, which pulls
from environment variables. See backend/.env.example for the full list.

Public API
----------
s3_service.upload_file(local_path, s3_key)  → s3_uri
s3_service.get_presigned_url(s3_key)        → https://...
s3_service.enabled                          → bool
upload_file_to_s3(local_path, s3_key)       → s3_uri
download_file_from_s3(s3_key, local_path)   → local_path_str
"""

import logging
from pathlib import Path
from typing import Optional, Union

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import s3_config

logger = logging.getLogger(__name__)


class S3UploadError(Exception):
    """Raised when an S3 operation fails."""


class S3Service:

    def __init__(self) -> None:
        self._client: Optional[object] = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return s3_config.enabled

    def upload_file(self, local_path: Union[str, Path], s3_key: str) -> str:
        """
        Upload *local_path* to S3 under *s3_key*.

        Parameters
        ----------
        local_path : Path to the local file to upload.
        s3_key     : Full S3 object key (e.g. "repositories/abc123-my-repo.zip").

        Returns
        -------
        The S3 URI:  s3://<bucket>/<key>
        """
        local_path = Path(local_path)
        if not local_path.exists():
            raise S3UploadError(f"File not found for S3 upload: {local_path}")

        bucket = s3_config.bucket_name
        try:
            client = self._get_client()
            client.upload_file(
                Filename=str(local_path),
                Bucket=bucket,
                Key=s3_key,
                ExtraArgs={"ServerSideEncryption": "AES256"},
            )
            uri = f"s3://{bucket}/{s3_key}"
            logger.info("Uploaded %s → %s", local_path.name, uri)
            return uri

        except (BotoCoreError, ClientError) as exc:
            raise S3UploadError(
                f"Failed to upload {local_path.name} to s3://{bucket}/{s3_key}: {exc}"
            ) from exc

    def get_presigned_url(self, s3_key: str) -> str:
        """
        Generate a pre-signed HTTPS download URL for *s3_key*.

        The URL is valid for s3_config.presigned_expiry_seconds seconds
        (default 3600 = 1 hour).
        """
        bucket = s3_config.bucket_name
        try:
            client = self._get_client()
            url = client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": s3_key},
                ExpiresIn=s3_config.presigned_expiry_seconds,
            )
            return url
        except (BotoCoreError, ClientError) as exc:
            raise S3UploadError(
                f"Failed to generate pre-signed URL for {s3_key}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_client(self):
        """Lazily create and cache the boto3 S3 client."""
        if self._client is None:
            kwargs = {"region_name": s3_config.region}
            # Explicit credentials — used in local dev.
            # On AWS infrastructure (EC2/ECS/Lambda) leave these blank and
            # boto3 will pick up the IAM role automatically.
            if s3_config.access_key_id and s3_config.secret_access_key:
                kwargs["aws_access_key_id"] = s3_config.access_key_id
                kwargs["aws_secret_access_key"] = s3_config.secret_access_key
            self._client = boto3.client("s3", **kwargs)
        return self._client


# Module-level singleton
s3_service = S3Service()


def upload_file_to_s3(local_path: Union[str, Path], s3_key: str) -> str:
    """Convenience functional wrapper around s3_service.upload_file."""
    return s3_service.upload_file(local_path, s3_key)


def download_file_from_s3(s3_key: str, local_path: Union[str, Path]) -> str:
    """Convenience functional wrapper to download an object from S3."""
    client = s3_service._get_client()
    local_path = Path(local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    client.download_file(s3_config.bucket_name, s3_key, str(local_path))
    return str(local_path)
