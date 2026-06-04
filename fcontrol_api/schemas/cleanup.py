from pydantic import BaseModel


class CleanupTaskPreview(BaseModel):
    task_name: str
    description: str
    count: int


class CleanupPreviewResponse(BaseModel):
    tasks: list[CleanupTaskPreview]
    total_records: int


class CleanupTaskResultOut(BaseModel):
    task_name: str
    status: str
    rows_affected: int
    duration_seconds: float
    errors: list[str]
    details: dict


class CleanupRunResponse(BaseModel):
    tasks: list[CleanupTaskResultOut]
    total_deleted: int
    executed_at: str
