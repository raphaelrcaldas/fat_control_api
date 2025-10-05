from pydantic import BaseModel, Field


class Token(BaseModel):
    access_token: str
    token_type: str
    first_login: bool


class FormAuth(BaseModel):
    saram: int = Field(gt=1000000, lt=9999999)
    password: str
