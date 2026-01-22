from pydantic import BaseModel, Field


class Token(BaseModel):
    access_token: str
    token_type: str
    first_login: bool


class FormAuth(BaseModel):
    saram: str = Field(min_length=7, max_length=7)
    password: str
