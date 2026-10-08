from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
    field_validator,
)

from fcontrol_api.schemas.users import UserPublic

# Campos obrigatórios da conta: sem espaços nas pontas e nunca vazios.
TextoObrigatorio = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]
# Espelha a coluna Numeric(14, 2): valor fora disso estourava no banco (500)
# ou perdia a terceira casa decimal em silêncio.
Valor = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]


class DadosBancariosBase(BaseModel):
    banco: TextoObrigatorio
    codigo_banco: TextoObrigatorio
    agencia: TextoObrigatorio
    conta: TextoObrigatorio

    remuneracao: Optional[Valor] = None
    mes_ano: Optional[date] = None
    aux_transp: Optional[Valor] = None

    model_config = ConfigDict(from_attributes=True)


class DadosBancariosCreate(DadosBancariosBase):
    user_id: int


class DadosBancariosUpdate(DadosBancariosBase):
    """Atualização parcial: só o que vier no corpo é gravado.

    Os quatro campos da conta podem ser omitidos, mas não enviados como
    `null` — as colunas são NOT NULL e o `setattr` do handler levava a um
    500 de integridade.
    """

    banco: Optional[TextoObrigatorio] = None
    codigo_banco: Optional[TextoObrigatorio] = None
    agencia: Optional[TextoObrigatorio] = None
    conta: Optional[TextoObrigatorio] = None

    @field_validator('banco', 'codigo_banco', 'agencia', 'conta')
    @classmethod
    def rejeitar_nulo(cls, v: Optional[str]) -> str:
        if v is None:
            raise ValueError('não pode ser nulo')
        return v


class DadosBancariosPublic(DadosBancariosBase):
    # A restrição vale para a entrada; a saída devolve o que está no banco.
    banco: str
    codigo_banco: str
    agencia: str
    conta: str
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    @field_serializer('remuneracao', 'aux_transp')
    def serialize_decimal(self, v: Optional[Decimal]) -> Optional[float]:
        return float(v) if v is not None else None


class DadosBancariosWithUser(DadosBancariosPublic):
    user: UserPublic


class RemuneracaoMilitar(BaseModel):
    """Projeção mínima para quem só precisa do valor da remuneração.

    Existe para não trafegar banco/agência/conta em telas que só usam a
    remuneração como base de cálculo (ex.: propostas de comissionamento).
    Militar sem cadastro devolve `remuneracao=None` — ausência de dado é
    resposta normal aqui, não erro.
    """

    user_id: int
    remuneracao: Optional[Decimal] = None
    # Mês de referência da remuneração — procedência do valor.
    mes_ano: Optional[date] = None

    @field_serializer('remuneracao')
    def serialize_decimal(self, v: Optional[Decimal]) -> Optional[float]:
        return float(v) if v is not None else None


class DadosBancariosBulkDelete(BaseModel):
    ids: list[int] = Field(min_length=1)


class DadosBancariosBulkDeleteResponse(BaseModel):
    deleted: int
