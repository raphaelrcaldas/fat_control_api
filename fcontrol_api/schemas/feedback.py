from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fcontrol_api.enums.feedback import FeedbackStatusEnum, FeedbackTipoEnum


class FeedbackUserOut(BaseModel):
    """Identificação mínima de quem enviou/respondeu.

    Não reusa `UserPublic` de propósito: aquele arrasta `posto` e o
    histórico de promoções (dois selectin por linha) para exibir um nome
    no topo de um cartão.
    """

    id: int
    p_g: str
    nome_guerra: str

    model_config = ConfigDict(from_attributes=True)


class FeedbackCreate(BaseModel):
    tipo: FeedbackTipoEnum
    titulo: str = Field(min_length=3, max_length=120)
    descricao: str = Field(min_length=10, max_length=2000)
    rota: str | None = Field(default=None, max_length=120)


class FeedbackUpdate(BaseModel):
    """Tratamento do feedback pela administração (status e/ou resposta)."""

    status: FeedbackStatusEnum | None = None
    resposta: str | None = Field(default=None, max_length=2000)

    @model_validator(mode='after')
    def pelo_menos_um_campo(self) -> 'FeedbackUpdate':
        if self.status is None and self.resposta is None:
            raise ValueError('Informe status e/ou resposta')
        return self


class FeedbackOut(BaseModel):
    id: int
    user_id: int
    uae: str
    tipo: FeedbackTipoEnum
    titulo: str
    descricao: str
    rota: str | None = None
    status: FeedbackStatusEnum
    resposta: str | None = None
    respondido_em: datetime | None = None
    created_at: datetime
    autor: FeedbackUserOut
    respondente: FeedbackUserOut | None = None

    model_config = ConfigDict(from_attributes=True)
