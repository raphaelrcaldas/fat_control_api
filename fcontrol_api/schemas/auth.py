from pydantic import BaseModel, Field


class Token(BaseModel):
    access_token: str
    token_type: str
    first_login: bool


class DevTokenResponse(BaseModel):
    access_token: str
    token_type: str
    target_user: str
    expires_in_days: int


class FormAuth(BaseModel):
    saram: str = Field(min_length=7, max_length=7)
    password: str


class SwitchOrg(BaseModel):
    # None = alternar para o escopo de sistema (vínculo com org NULL).
    organizacao_id: str | None = None
