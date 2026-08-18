"""Schemas das propostas de comissionamento (sandbox).

Espelham `client/services/routes/cegep/propostas.ts` — manter os dois
consistentes. Dois pontos que não são óbvios:

- **Leitura devolve `linha.user`; escrita manda só `user_id`.** O militar é
  denormalizado apenas para exibir; sem o join a tela perde o nome de todos
  os militares logo depois de salvar.
- **O PUT manda a proposta inteira** (todos os cenários e linhas). O front
  edita um rascunho local e grava de uma vez; o backend sincroniza contra o
  que existe, preservando os ids que voltaram no eco.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    model_validator,
)

from fcontrol_api.schemas.users import UserPublic

#: Ids da paleta de cenários. A UI mapeia cada id para classes Tailwind
#: literais — aqui é só identidade, nunca cor css.
CenarioCorId = Literal[
    'sky', 'violet', 'emerald', 'rose', 'cyan', 'indigo', 'amber'
]

PropostaStatus = Literal['rascunho']

#: Quantidade de ajuda de custo: lista fechada do domínio, a mesma do
#: `ComissForm` (step 0,5 e teto 2; zero reprova).
QtdAjuda = Literal[0.5, 1, 1.5, 2]


#: Teto do valor-base: a coluna é `Numeric(14, 2)`, e sem este limite um
#: valor com dígitos demais estoura no banco (`numeric field overflow`) —
#: 500 no lugar do 422 que o usuário precisa ler.
BASE_MAXIMA = Decimal('999999999999.99')


class LinhaBase(BaseModel):
    user_id: int

    base_ab: Decimal = Field(ge=0, le=BASE_MAXIMA)
    qtd_ab: QtdAjuda
    ano_ab: int = Field(ge=2026, le=2100)

    base_fc: Decimal = Field(ge=0, le=BASE_MAXIMA)
    qtd_fc: QtdAjuda
    ano_fc: int = Field(ge=2026, le=2100)


class LinhaIn(LinhaBase):
    #: Ausente/nulo em linha ainda não persistida.
    id: Optional[int] = None


class LinhaOut(LinhaBase):
    id: int
    #: Denormalizado só para exibição.
    user: Optional[UserPublic] = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer('base_ab', 'base_fc')
    def serialize_decimal(self, v: Decimal) -> float:
        return float(v)


class CenarioIn(BaseModel):
    id: Optional[int] = None
    nome: str = Field(min_length=1, max_length=60)
    cor: CenarioCorId
    linhas: list[LinhaIn] = Field(default_factory=list)


class CenarioOut(BaseModel):
    id: int
    nome: str
    cor: str
    linhas: list[LinhaOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class PropostaCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    ano_ref: int = Field(ge=2026, le=2100)


class PropostaUpdate(PropostaCreate):
    cenarios: list[CenarioIn] = Field(default_factory=list)

    @model_validator(mode='after')
    def check_exercicios(self):
        """As duas regras que ligam a linha ao exercício da proposta.

        Moram aqui, e não só nos CHECKs da tabela, porque violação de
        constraint vira 500: quem preenche merece 422 dizendo o que está
        errado. O banco segue como rede de segurança para escrita que não
        passe por este schema.
        """
        for cenario in self.cenarios:
            vistos: set[int] = set()
            for linha in cenario.linhas:
                # O mesmo militar duas vezes no cenário violaria o UNIQUE e
                # sairia como 500. Entre cenários diferentes é permitido.
                if linha.user_id in vistos:
                    raise ValueError(
                        f'O militar {linha.user_id} aparece duas vezes no '
                        f'cenário "{cenario.nome}".'
                    )
                vistos.add(linha.user_id)

                if linha.ano_ab != self.ano_ref:
                    raise ValueError(
                        'A abertura tem de cair no exercício da proposta '
                        f'({self.ano_ref}); recebido {linha.ano_ab}.'
                    )
                if linha.ano_fc < linha.ano_ab:
                    raise ValueError(
                        'O fechamento não pode cair antes do exercício da '
                        f'abertura ({linha.ano_fc} < {linha.ano_ab}).'
                    )
        return self


class PropostaOut(BaseModel):
    id: int
    nome: str
    ano_ref: int
    status: PropostaStatus
    cenarios: list[CenarioOut] = Field(default_factory=list)
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PropostaListItem(BaseModel):
    id: int
    nome: str
    ano_ref: int
    status: PropostaStatus
    cenarios_count: int
    updated_at: datetime
