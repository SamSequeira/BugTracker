from pydantic import BaseModel , HttpUrl

class RepositoryCloneRequest(BaseModel):
    repository_url : HttpUrl

class RepositoryCloneResponse(BaseModel):
    message: str
    repository_id: str
    repository_name: str
    repository_path: str
