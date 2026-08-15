from typing import Optional
from pydantic import BaseModel, HttpUrl


class RepositoryCloneRequest(BaseModel):
    repository_url: HttpUrl


class RepositoryCloneResponse(BaseModel):
    message: str
    repository_id: str
    repository_name: str
    repository_path: str
    s3_uri: Optional[str] = None   # e.g. s3://my-bucket/repositories/abc123-my-repo.zip
    s3_key: Optional[str] = None   # e.g. repositories/abc123-my-repo.zip
