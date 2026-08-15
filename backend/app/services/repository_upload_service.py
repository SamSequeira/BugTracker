import shutil
import uuid
import zipfile
from pathlib import Path

from fastapi import UploadFile


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

    async def upload_file(self, file: UploadFile) -> dict:
        if not file.filename:
            raise RepositoryUploadError("No file was provided.")

        filename = Path(file.filename).name
        if not filename:
            raise RepositoryUploadError("Invalid file name.")

        repository_id = str(uuid.uuid4())
        repository_name = Path(filename).stem
        # Folder name: <uuid>-<repo-name>
        repository_path = self.workspace / f"{repository_id}-{repository_name}"
        repository_path.mkdir(parents=True, exist_ok=True)

        try:
            if filename.lower().endswith(".zip"):
                await self._save_and_extract_zip(file, repository_path)
            else:
                await self._save_code_file(file, repository_path / filename)

        except RepositoryUploadError:
            self._cleanup(repository_path)
            raise
        except Exception as error:
            self._cleanup(repository_path)
            raise RepositoryUploadError(
                "Unable to process the uploaded file."
            ) from error

        return {
            "repository_id": repository_id,
            "repository_name": repository_name,
            "repository_path": str(repository_path),
        }

    async def _save_code_file(self, file: UploadFile, destination: Path) -> None:
        extension = destination.suffix.lower()
        if extension not in self.ALLOWED_CODE_EXTENSIONS:
            raise RepositoryUploadError(
                f"Unsupported file type: {extension or 'unknown'}."
            )
        await self._save_stream(file, destination)

    async def _save_and_extract_zip(self, file: UploadFile, destination: Path) -> None:
        zip_path = destination / "_upload.zip"
        await self._save_stream(file, zip_path)
        try:
            with zipfile.ZipFile(zip_path, "r") as archive:
                for member in archive.infolist():
                    member_path = destination / member.filename
                    if not self._is_safe_path(destination, member_path):
                        raise RepositoryUploadError(
                            "The uploaded ZIP contains an unsafe file path."
                        )
                archive.extractall(destination)
        except zipfile.BadZipFile as error:
            raise RepositoryUploadError(
                "The uploaded file is not a valid ZIP archive."
            ) from error
        finally:
            zip_path.unlink(missing_ok=True)

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
    def _is_safe_path(base_path: Path, target_path: Path) -> bool:
        base = base_path.resolve()
        target = target_path.resolve()
        return target == base or base in target.parents

    @staticmethod
    def _cleanup(path: Path) -> None:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


repository_upload_service = RepositoryUploadService()
