from datetime import datetime

from pydantic import BaseModel

from fcontrol_api.enums.posto_grad import PostoGradEnum


class UserSummary(BaseModel):
    id: int
    p_g: PostoGradEnum
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
