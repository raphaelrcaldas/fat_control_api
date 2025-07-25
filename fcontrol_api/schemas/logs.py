from datetime import datetime

from pydantic import BaseModel


class UserSummary(BaseModel):
    id: int
    p_g: str
    nome_guerra: str


class UserActionLogOut(BaseModel):
    id: int
    user: UserSummary
    action: str
    resource: str
    resource_id: int | None
    before: str | None
    after: str | None
    timestamp: datetime
