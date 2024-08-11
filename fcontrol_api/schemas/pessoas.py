from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class PessoaSchema(BaseModel):
    pg: str
    nome_guerra: str
    nome_completo: str | None
    ult_promo: datetime | None
    id_fab: str | None
    saram: str | None
    cpf: str | None
    nasc: datetime | None
    celular: str | None
    email_pess: EmailStr | None
    email_fab: EmailStr | None
    unidade: str


class PessoaPublic(BaseModel):
    pg: str
    nome_guerra: str
    unidade: str
    # saram: str | None
    model_config = ConfigDict(from_attributes=True)


class ListPessoa(BaseModel):
    data: list[PessoaPublic]
