from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IssueStatusResponse(BaseModel):
    id: str
    candidate_issue_id: str

    status: str

    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )