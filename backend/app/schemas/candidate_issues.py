from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CandidateIssueResponse(BaseModel):
    id: str
    analysis_run_id: str

    title: str
    description: str

    file_path: str
    line_number: int | None = None

    severity: str
    urgency: str

    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )