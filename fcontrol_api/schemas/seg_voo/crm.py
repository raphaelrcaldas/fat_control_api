from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CrmBase(BaseModel):
    data_realizacao: date | None = None
    data_validade: date | None = None

    model_config = ConfigDict(from_attributes=True)


class CrmUpdate(CrmBase):
    @model_validator(mode='after')
    def validade_apos_realizacao(self) -> 'CrmUpdate':
        if (
            self.data_realizacao is not None
            and self.data_validade is not None
            and self.data_validade < self.data_realizacao
        ):
            raise ValueError(
                'data_validade nao pode ser anterior a data_realizacao'
            )
        return self


class CrmPublic(CrmBase):
    id: int
    user_id: int


class TripCrmOut(BaseModel):
    trip_id: int
    user_id: int
    p_g: str
    nome_guerra: str
    nome_completo: str | None
    saram: str | None
    telefone: str | None
    crm: CrmPublic | None = None

    model_config = ConfigDict(from_attributes=True)


class CrmOrfaoPublic(BaseModel):
    """Militar inativo com certificado CRM (limpeza)."""

    user_id: int
    p_g: str
    nome_guerra: str
    nome_completo: str | None


class CrmOrfaosResumo(BaseModel):
    total_registros: int
    itens: list[CrmOrfaoPublic]


class CrmOrfaosDelete(BaseModel):
    user_ids: list[int] = Field(min_length=1)


class CrmOrfaosDeleteResponse(BaseModel):
    deleted: int
