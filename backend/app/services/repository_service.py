"""
repository_service.py
---------------------
Handles GitHub repository cloning:
  1. Clone into repositories/<uuid>-<name>/
  2. Zip the cloned folder
  3. Upload the ZIP to S3 (if S3 is enabled)
  4. Remove the ZIP (cloned folder stays for analysis)
"""

import asyncio
import logging
import shutil
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.repository import Repository
from app.repositories.repository_repo import repository_repository
from app.utils.git import GitCloneError, clone_repository
from app.services.s3_service import S3UploadError, s3_service
from app.core.config import s3_config

logger = logging.getLogger(__name__)


class RepositoryCloneService:

    def __init__(self) -> None:
        self.workspace = Path("repositories")
        self.workspace.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def clone_repository(
        self, repository_url: str, db: AsyncSession
    ) -> dict:
        repository_id = str(uuid.uuid4())
        repository_name = self._get_repository_name(repository_url)
        # Folder: repositories/<uuid>-<repo-name>/
        repository_path = self.workspace / f"{repository_id}-{repository_name}"

        try:
            await asyncio.to_thread(
                clone_repository,
                repository_url,
                repository_path,
            )
        except GitCloneError:
            if repository_path.exists():
                shutil.rmtree(repository_path, ignore_errors=True)
            raise

        # ------------------------------------------------------------------
        # A persisted Repository must point to a durable S3 archive.
        # ------------------------------------------------------------------
        s3_uri: str | None = None
        s3_key: str | None = None

        if not s3_service.enabled:
            raise S3UploadError("S3 uploads are not configured.")

        if s3_service.enabled:
            zip_path = repository_path.parent / f"{repository_id}-{repository_name}.zip"
            try:
                await asyncio.to_thread(
                    self._zip_directory, repository_path, zip_path
                )
                s3_key = f"{s3_config.prefix}/{repository_id}-{repository_name}.zip"
                s3_uri = s3_service.upload_file(zip_path, s3_key)
            finally:
                zip_path.unlink(missing_ok=True)
        else:
            logger.debug("S3 uploads disabled — skipping for %s", repository_name)

        repository = Repository(
            id=repository_id,
            name=repository_name,
            source_url=repository_url,
            s3_key=s3_key,
        )
        try:
            await repository_repository.create(db, repository)
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        result = {
            "repository_id": repository.id,
            "repository_name": repository_name,
        }
        result["s3_uri"] = s3_uri
        result["s3_key"] = s3_key

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_repository_name(repository_url: str) -> str:
        parsed_url = urlparse(repository_url)
        path = parsed_url.path.rstrip("/")
        if not path:
            raise ValueError(
                "Repository URL does not contain a repository name."
            )
        repository_name = path.split("/")[-1]
        if repository_name.endswith(".git"):
            repository_name = repository_name[:-4]
        if not repository_name:
            raise ValueError("Invalid repository name.")
        return repository_name

    @staticmethod
    def _zip_directory(source_dir: Path, output_zip: Path) -> None:
        """Zip all files in source_dir into output_zip."""
        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in source_dir.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(source_dir))


repository_service = RepositoryCloneService()
