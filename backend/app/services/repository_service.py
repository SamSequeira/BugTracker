import asyncio
import shutil
import uuid
from pathlib import Path
from urllib.parse import urlparse

from app.utils.git import GitCloneError, clone_repository


class RepositoryCloneService:

    def __init__(self) -> None:
        self.workspace = Path("repositories")
        self.workspace.mkdir(parents=True, exist_ok=True)

    async def clone_repository(
        self,
        repository_url: str,
    ) -> dict:

        repository_id = str(uuid.uuid4())

        repository_name = self._get_repository_name(
            repository_url
        )

        repository_path = self.workspace / repository_id

        try:
            await asyncio.to_thread(
                clone_repository,
                repository_url,
                repository_path,
            )

        except GitCloneError:
            if repository_path.exists():
                shutil.rmtree(
                    repository_path,
                    ignore_errors=True,
                )

            raise

        return {
            "repository_id": repository_id,
            "repository_name": repository_name,
            "repository_path": str(repository_path),
        }

    @staticmethod
    def _get_repository_name(
        repository_url: str,
    ) -> str:

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
            raise ValueError(
                "Invalid repository name."
            )

        return repository_name


repository_service = RepositoryCloneService()