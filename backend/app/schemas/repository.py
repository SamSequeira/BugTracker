from datetime import datetime
from typing import Optional

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


class AnalysisStatusResponse(BaseModel):
    """
    Read-only status snapshot for the latest AnalysisRun belonging to a repository.

    status values:
      "none"      – no AnalysisRun exists yet for this repository
      "running"   – analysis is currently in progress
      "completed" – analysis finished successfully
      "failed"    – analysis encountered an error

    duration_seconds is computed from actual timestamps; it is None when
    completed_at is not yet recorded (e.g. status="running").
    """
    repository_id: str
    latest_run_id: Optional[str] = None
    status: str  # "none" | "running" | "completed" | "failed"
    total_files: int = 0
    supported_files: int = 0
    candidate_issues_count: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)