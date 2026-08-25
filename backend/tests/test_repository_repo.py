"""
test_repository_repo.py
------------------------
Unit tests for RepositoryRepository DAL and its integration in repository services.
"""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

from app.models.repository import Repository
from app.repositories.repository_repo import RepositoryRepository
from app.services.repository_service import repository_service
from app.services.repository_upload_service import repository_upload_service


@pytest.mark.asyncio
async def test_repository_repo_create():
    repo_dal = RepositoryRepository()
    mock_db = AsyncMock()
    mock_db.add = MagicMock()

    repo = Repository(
        id=str(uuid.uuid4()),
        name="test-repo",
        source_url="https://github.com/example/test-repo",
        s3_key="repositories/test.zip",
    )

    res = await repo_dal.create(mock_db, repo)

    assert res.id == repo.id
    mock_db.add.assert_called_once_with(repo)
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_repository_repo_get_by_id():
    repo_dal = RepositoryRepository()
    mock_db = AsyncMock()
    repo_id = str(uuid.uuid4())

    expected_repo = Repository(
        id=repo_id,
        name="test-repo",
        s3_key="repositories/test.zip",
    )
    mock_db.get.return_value = expected_repo

    fetched = await repo_dal.get_by_id(mock_db, repo_id)

    assert fetched == expected_repo
    mock_db.get.assert_called_once_with(Repository, repo_id)


@pytest.mark.asyncio
async def test_clone_service_uses_repository_dal():
    mock_db = AsyncMock()
    repo_url = "https://github.com/example/demo.git"

    with patch("app.services.repository_service.clone_repository"), \
         patch("app.services.repository_service.s3_service.upload_file", return_value="s3://bucket/key.zip"), \
         patch("app.services.s3_service.S3Service.enabled", new_callable=PropertyMock, return_value=True), \
         patch("app.services.repository_service.RepositoryCloneService._zip_directory"), \
         patch("app.services.repository_service.repository_repository.create", new_callable=AsyncMock) as mock_dal_create:

        result = await repository_service.clone_repository(repo_url, mock_db)

        assert "repository_id" in result
        assert result["repository_name"] == "demo"
        mock_dal_create.assert_called_once()
        mock_db.commit.assert_called_once()
