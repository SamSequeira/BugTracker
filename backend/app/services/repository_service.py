import asyncio
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from app.utils.git import GitCloneError, clone_repository
from app.services.s3_service import upload_file_to_s3


class RepositoryCloneService:

    def __init__(self) -> None:
        self.workspace = Path("repositories")
        self.workspace.mkdir(
            parents=True,
            exist_ok=True,
        )

    async def clone_repository(
        self,
        repository_url: str,
    ) -> dict:

        repository_id = str(uuid.uuid4())

        repository_name = self._get_repository_name(
            repository_url
        )

        # Temporary directory
        temporary_directory = Path(
            tempfile.mkdtemp(
                prefix="bugtracker_"
            )
        )

        repository_path = (
            temporary_directory / repository_name
        )

        try:

            # -----------------------------------------
            # 1. Clone GitHub repository
            # -----------------------------------------

            await asyncio.to_thread(
                clone_repository,
                repository_url,
                repository_path,
            )

            # -----------------------------------------
            # 2. Create ZIP
            # -----------------------------------------

            zip_path = (
                temporary_directory
                / f"{repository_name}.zip"
            )

            self._create_zip(
                repository_path,
                zip_path,
            )

            # -----------------------------------------
            # 3. Upload ZIP to S3
            # -----------------------------------------

            s3_key = (
                f"repositories/{repository_name}.zip"
            )

            await asyncio.to_thread(
                upload_file_to_s3,
                str(zip_path),
                s3_key,
            )

            # -----------------------------------------
            # 4. Return team's existing response format
            # -----------------------------------------

            return {
                "repository_id": repository_id,
                "repository_name": repository_name,
                "repository_path": str(repository_path),
            }

        finally:

            # -----------------------------------------
            # 5. Delete temporary local repository
            # -----------------------------------------

            if temporary_directory.exists():
                shutil.rmtree(
                    temporary_directory,
                    ignore_errors=True,
                )

    @staticmethod
    def _get_repository_name(
        repository_url: str,
    ) -> str:

        parsed_url = urlparse(
            repository_url
        )

        path = parsed_url.path.rstrip("/")

        if not path:
            raise ValueError(
                "Repository URL does not contain a repository name."
            )

        repository_name = path.split("/")[-1]

        if repository_name.endswith(".git"):
            repository_name = repository_name[:-4]

        if not repository_name:
            raise ValueError(
                "Invalid repository name."
            )

        return repository_name

    @staticmethod
    def _create_zip(
        source_directory: Path,
        output_zip: Path,
    ) -> None:

        with zipfile.ZipFile(
            output_zip,
            "w",
            zipfile.ZIP_DEFLATED,
        ) as zip_file:

            for file_path in source_directory.rglob("*"):

                if file_path.is_file():

                    zip_file.write(
                        file_path,
                        file_path.relative_to(
                            source_directory
                        ),
                    )


repository_service = RepositoryCloneService()