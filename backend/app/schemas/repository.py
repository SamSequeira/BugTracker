from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl


class RepositoryCloneRequest(BaseModel):
    repository_url: HttpUrl


class RepositoryCloneResponse(BaseModel):
    message: str
    repository_id: str
    repository_name: str
    s3_uri: str | None = None
    s3_key: str | None = None


class RepositoryResponse(BaseModel):
    id: str
    name: str
    source_url: str | None = None
    s3_key: str

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )