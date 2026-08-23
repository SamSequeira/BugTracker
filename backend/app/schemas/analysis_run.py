from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AnalysisRunResponse(BaseModel):
    id: str
    repository_id: str

    status: str

    total_files: int | None = None
    supported_files: int | None = None
    candidate_issues_count: int | None = None

    error_message: str | None = None

    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )