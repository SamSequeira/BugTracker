"""
repository_upload_service.py
-----------------------------
Handles ZIP / single-file uploads:
  1. Save to local disk under repositories/<uuid>-<name>/
  2. Extract ZIP contents locally (for analysis)
  3. Upload the original ZIP to S3 (if S3 is enabled)
  4. Persist repository metadata to PostgreSQL
"""

import logging
import shutil
import uuid
import zipfile
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.repository import Repository
from app.repositories.repository_repo import repository_repository
from app.services.s3_service import S3UploadError, s3_service
from app.core.config import s3_config

logger = logging.getLogger(__name__)


class RepositoryUploadError(Exception):
    """Raised when a repository upload cannot be processed."""


class RepositoryUploadService:

    MAX_FILE_SIZE = 1024 * 1024 * 1024  # 1 GB

    ALLOWED_CODE_EXTENSIONS = {
        ".py", ".java", ".js", ".jsx", ".ts", ".tsx",
        ".c", ".cpp", ".h", ".hpp", ".cs", ".go",
        ".rs", ".php", ".rb", ".swift", ".kt", ".kts",
    }

    def __init__(self) -> None:
        self.workspace = Path("repositories")
        self.workspace.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def upload_file(self, file: UploadFile, db: AsyncSession, user_id: Optional[str] = None) -> dict:
        if not file.filename:
            raise RepositoryUploadError("No file was provided.")

        filename = Path(file.filename).name
        if not filename:
            raise RepositoryUploadError("Invalid file name.")

        repository_id = str(uuid.uuid4())
        repository_name = Path(filename).stem
        # Folder: repositories/<uuid>-<repo-name>/
        repository_path = self.workspace / f"{repository_id}-{repository_name}"
        repository_path.mkdir(parents=True, exist_ok=True)

        try:
            if filename.lower().endswith(".zip"):
                zip_local_path = await self._save_and_extract_zip(
                    file, repository_path, filename
                )
            else:
                zip_local_path = None
                await self._save_code_file(file, repository_path / filename)

        except RepositoryUploadError:
            self._cleanup(repository_path)
            raise
        except Exception as error:
            self._cleanup(repository_path)
            raise RepositoryUploadError(
                "Unable to process the uploaded file."
            ) from error

        # ------------------------------------------------------------------
        # S3 upload (if configured/enabled)
        # ------------------------------------------------------------------
        s3_uri: str | None = None
        s3_key: str | None = None

        if s3_service.enabled:
            try:
                if zip_local_path and zip_local_path.exists():
                    s3_key = f"{s3_config.prefix}/{repository_id}-{repository_name}.zip"
                    s3_uri = s3_service.upload_file(zip_local_path, s3_key)
                    zip_local_path.unlink(missing_ok=True)
                else:
                    zip_local_path = repository_path / f"{repository_name}.zip"
                    self._zip_directory(repository_path, zip_local_path)
                    s3_key = f"{s3_config.prefix}/{repository_id}-{repository_name}.zip"
                    s3_uri = s3_service.upload_file(zip_local_path, s3_key)
                    zip_local_path.unlink(missing_ok=True)

            except S3UploadError as err:
                logger.error("S3 upload failed for repository %s: %s", repository_name, err)
                raise
        else:
            logger.info("S3 uploads disabled or unconfigured — storing repository locally for %s", repository_name)

        repository = Repository(
            id=repository_id,
            user_id=user_id,
            name=repository_name,
            source_url=None,
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

    async def _save_code_file(self, file: UploadFile, destination: Path) -> None:
        extension = destination.suffix.lower()
        if extension not in self.ALLOWED_CODE_EXTENSIONS:
            raise RepositoryUploadError(
                f"Unsupported file type: {extension or 'unknown'}."
            )
        await self._save_stream(file, destination)

    async def _save_and_extract_zip(
        self,
        file: UploadFile,
        destination: Path,
        original_filename: str,
    ) -> Path:
        """
        Save the uploaded ZIP to disk and extract it.
        Returns the path to the saved ZIP file (caller decides when to delete it).
        """
        zip_path = destination / original_filename
        await self._save_stream(file, zip_path)

        try:
            with zipfile.ZipFile(zip_path, "r") as archive:
                infolist = archive.infolist()
                if not infolist:
                    raise RepositoryUploadError("The uploaded ZIP archive is empty.")
                for member in infolist:
                    member_path = destination / member.filename
                    if not self._is_safe_path(destination, member_path):
                        raise RepositoryUploadError(
                            "The uploaded ZIP contains an unsafe file path."
                        )
                archive.extractall(destination)
        except zipfile.BadZipFile as error:
            zip_path.unlink(missing_ok=True)
            raise RepositoryUploadError(
                "The uploaded file is not a valid ZIP archive."
            ) from error

        return zip_path

    async def _save_stream(self, file: UploadFile, destination: Path) -> None:
        total_size = 0
        chunk_size = 1024 * 1024
        try:
            with destination.open("wb") as output:
                while True:
                    chunk = await file.read(chunk_size)
                    if not chunk:
                        break
                    total_size += len(chunk)
                    if total_size > self.MAX_FILE_SIZE:
                        raise RepositoryUploadError(
                            "Uploaded file exceeds the 1 GB size limit."
                        )
                    output.write(chunk)
        finally:
            await file.close()

    @staticmethod
    def _zip_directory(source_dir: Path, output_zip: Path) -> None:
        """Zip all files inside source_dir into output_zip."""
        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in source_dir.rglob("*"):
                if file_path.is_file() and file_path != output_zip:
                    zf.write(file_path, file_path.relative_to(source_dir))

    @staticmethod
    def _is_safe_path(base_path: Path, target_path: Path) -> bool:
        base = base_path.resolve()
        target = target_path.resolve()
        return target == base or base in target.parents

    @staticmethod
    def _cleanup(path: Path) -> None:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


repository_upload_service = RepositoryUploadService()
"""
repository_upload_service.py
-----------------------------
Handles ZIP / single-file uploads:
  1. Save to local disk under repositories/<uuid>-<name>/
  2. Extract ZIP contents locally (for analysis)
  3. Upload the original ZIP to S3 (if S3 is enabled)
"""

import logging
import shutil
import uuid
import zipfile
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.repository import Repository
from app.repositories.repository_repo import repository_repository
from app.services.s3_service import S3UploadError, s3_service
from app.core.config import s3_config

logger = logging.getLogger(__name__)


class RepositoryUploadError(Exception):
    """Raised when a repository upload cannot be processed."""


class RepositoryUploadService:

    MAX_FILE_SIZE = 1024 * 1024 * 1024  # 1 GB

    ALLOWED_CODE_EXTENSIONS = {
        ".py", ".java", ".js", ".jsx", ".ts", ".tsx",
        ".c", ".cpp", ".h", ".hpp", ".cs", ".go",
        ".rs", ".php", ".rb", ".swift", ".kt", ".kts",
    }

    def __init__(self) -> None:
        self.workspace = Path("repositories")
        self.workspace.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def upload_file(self, file: UploadFile, db: AsyncSession, user_id: Optional[str] = None) -> dict:
        if not file.filename:
            raise RepositoryUploadError("No file was provided.")

        filename = Path(file.filename).name
        if not filename:
            raise RepositoryUploadError("Invalid file name.")

        repository_id = str(uuid.uuid4())
        repository_name = Path(filename).stem
        # Folder: repositories/<uuid>-<repo-name>/
        repository_path = self.workspace / f"{repository_id}-{repository_name}"
        repository_path.mkdir(parents=True, exist_ok=True)

        try:
            if filename.lower().endswith(".zip"):
                zip_local_path = await self._save_and_extract_zip(
                    file, repository_path, filename
                )
            else:
                zip_local_path = None
                await self._save_code_file(file, repository_path / filename)

        except RepositoryUploadError:
            self._cleanup(repository_path)
            raise
        except Exception as error:
            self._cleanup(repository_path)
            raise RepositoryUploadError(
                "Unable to process the uploaded file."
            ) from error

        # ------------------------------------------------------------------
        # S3 upload (non-fatal — local files remain available for analysis)
        # ------------------------------------------------------------------
        s3_uri: str | None = None
        s3_key: str | None = f"{s3_config.prefix}/{repository_id}-{repository_name}.zip"

        if s3_service.enabled:
            try:
                if zip_local_path and zip_local_path.exists():
                    # Use the original ZIP that was saved temporarily
                    s3_key = f"{s3_config.prefix}/{repository_id}-{repository_name}.zip"
                    s3_uri = s3_service.upload_file(zip_local_path, s3_key)
                    # Clean up temp ZIP now that it's in S3
                    zip_local_path.unlink(missing_ok=True)
                else:
                    # Single code file — zip it before uploading
                    zip_local_path = repository_path / f"{repository_name}.zip"
                    self._zip_directory(repository_path, zip_local_path)
                    s3_key = f"{s3_config.prefix}/{repository_id}-{repository_name}.zip"
                    s3_uri = s3_service.upload_file(zip_local_path, s3_key)
                    zip_local_path.unlink(missing_ok=True)

            except S3UploadError as exc:
                logger.warning("S3 upload failed for %s, falling back to local copy: %s", repository_name, exc)
        else:
            logger.debug("S3 uploads disabled — skipping for %s", repository_name)

        repository = Repository(
            id=repository_id,
            user_id=user_id,
            name=repository_name,
            source_url=None,
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

    async def _save_code_file(self, file: UploadFile, destination: Path) -> None:
        extension = destination.suffix.lower()
        if extension not in self.ALLOWED_CODE_EXTENSIONS:
            raise RepositoryUploadError(
                f"Unsupported file type: {extension or 'unknown'}."
            )
        await self._save_stream(file, destination)

    async def _save_and_extract_zip(
        self,
        file: UploadFile,
        destination: Path,
        original_filename: str,
    ) -> Path:
        """
        Save the uploaded ZIP to disk and extract it.
        Returns the path to the saved ZIP file (caller decides when to delete it).
        """
        zip_path = destination / original_filename
        await self._save_stream(file, zip_path)

        try:
            with zipfile.ZipFile(zip_path, "r") as archive:
                infolist = archive.infolist()
                if not infolist:
                    raise RepositoryUploadError("The uploaded ZIP archive is empty.")
                for member in infolist:
                    member_path = destination / member.filename
                    if not self._is_safe_path(destination, member_path):
                        raise RepositoryUploadError(
                            "The uploaded ZIP contains an unsafe file path."
                        )
                archive.extractall(destination)
        except zipfile.BadZipFile as error:
            zip_path.unlink(missing_ok=True)
            raise RepositoryUploadError(
                "The uploaded file is not a valid ZIP archive."
            ) from error

        return zip_path

    async def _save_stream(self, file: UploadFile, destination: Path) -> None:
        total_size = 0
        chunk_size = 1024 * 1024
        try:
            with destination.open("wb") as output:
                while True:
                    chunk = await file.read(chunk_size)
                    if not chunk:
                        break
                    total_size += len(chunk)
                    if total_size > self.MAX_FILE_SIZE:
                        raise RepositoryUploadError(
                            "Uploaded file exceeds the 1 GB size limit."
                        )
                    output.write(chunk)
        finally:
            await file.close()

    @staticmethod
    def _zip_directory(source_dir: Path, output_zip: Path) -> None:
        """Zip all files inside source_dir into output_zip."""
        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in source_dir.rglob("*"):
                if file_path.is_file() and file_path != output_zip:
                    zf.write(file_path, file_path.relative_to(source_dir))

    @staticmethod
    def _is_safe_path(base_path: Path, target_path: Path) -> bool:
        base = base_path.resolve()
        target = target_path.resolve()
        return target == base or base in target.parents

    @staticmethod
    def _cleanup(path: Path) -> None:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


repository_upload_service = RepositoryUploadService()
