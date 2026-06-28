from datetime import date, datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from fcontrol_api.enums.posto_grad import PostoGradEnum
from fcontrol_api.schemas.cidade import CidadeSchema
from fcontrol_api.schemas.etiquetas import EtiquetaSchema
from fcontrol_api.schemas.users import UserPublic
from fcontrol_api.utils.sanitize import TextoLivre, TextoMultilinha

# O número do documento é armazenado com zero-padding à esquerda de no
# mínimo 3 dígitos (ex.: '036'), sem truncar os maiores (ex.: '1999') —
# há ordens reais de 4 dígitos. Espelha o padStart(3) do frontend.
N_DOC_WIDTH = 3


def normalizar_n_doc(v) -> str:
    """Normaliza o número do documento para string com zero-padding.

    Aceita int ou str, valida que são apenas dígitos e aplica padding à
    esquerda de no mínimo `N_DOC_WIDTH` (sem truncar valores maiores).
    Fonte única usada na escrita e nos filtros, garantindo que o valor
    persistido e o buscado coincidam.
    """
    s = str(v).strip()
    if not s.isdigit():
        raise ValueError('Número do documento deve conter apenas dígitos')
    return s.zfill(N_DOC_WIDTH)


NumDoc = Annotated[str, BeforeValidator(normalizar_n_doc)]


class MissoesFilterParams(BaseModel):
    """
    Parâmetros de filtro e paginação para missões.

    Validação de entrada para prevenir SQL injection e DoS attacks.
    Todos os parâmetros são opcionais exceto page e per_page.
    """

    tipo_doc: Optional[str] = Field(
        None,
        max_length=50,
        description="Tipo(s) do documento (ex: 'om,os')",
    )

    n_doc: Optional[NumDoc] = Field(None, description='Número do documento')

    tipo: Optional[str] = Field(
        None,
        max_length=50,
        description="Tipo(s) da missão, separados por vírgula (ex: 'adm,opr')",
    )

    user_search: Optional[str] = Field(
        None,
        max_length=100,
        description='Nome de guerra para busca (busca parcial)',
    )

    city: Optional[str] = Field(
        None, max_length=100, description='Nome da cidade (busca parcial)'
    )

    ini: Optional[date] = Field(
        None, description='Data inicial de afastamento (filtro >= ini)'
    )

    fim: Optional[date] = Field(
        None, description='Data final de regresso (filtro <= fim)'
    )

    etiqueta_ids: Optional[str] = Field(
        None,
        pattern=r'^[\d,\s]+$',
        max_length=200,
        description="IDs de etiquetas separados por vírgula (ex: '1,2,3')",
    )

    page: int = Field(1, ge=1, description='Número da página (inicia em 1)')

    per_page: int = Field(
        20,
        ge=1,
        le=100,
        description='Itens por página (máximo 100 para prevenir DoS)',
    )

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class PernoiteFragMis(BaseModel):
    id: Optional[int] = None
    frag_id: Optional[int] = None
    acrec_desloc: bool
    data_ini: date
    data_fim: date
    meia_diaria: bool
    obs: TextoMultilinha
    cidade_id: int
    cidade: CidadeSchema
    model_config = ConfigDict(from_attributes=True)


class CidadePernoiteSchema(CidadeSchema):
    """Cidade com métricas de uso em pernoites (busca ranqueada)."""

    usos: int
    mais_usada: bool


class CustoVal(BaseModel):
    valor: float
    qtd: float


class CustoPernoiteOut(BaseModel):
    """Custo calculado de um pernoite para um pg+sit específico."""

    subtotal: float = 0
    ac_desloc: float = 0
    vals: list[CustoVal] = []
    dias: int = 0


class PernoiteWithCusto(PernoiteFragMis):
    """PernoiteFragMis com campos de custo calculados por custo_missao."""

    gp_cid: int = 3
    custo: CustoPernoiteOut | None = None


class UserFragMis(BaseModel):
    id: Optional[int] = None
    frag_id: Optional[int] = None
    user_id: int
    p_g: PostoGradEnum
    sit: Literal['c', 'd', 'g']
    user: UserPublic

    model_config = ConfigDict(from_attributes=True)


class FragMisSchema(BaseModel):
    id: Optional[int] = None
    n_doc: NumDoc
    tipo_doc: Literal['os', 'om']
    indenizavel: bool
    acrec_desloc: bool
    afast: datetime
    regres: datetime
    desc: TextoLivre
    obs: TextoMultilinha
    tipo: Literal['adm', 'tal', 'opr']
    pernoites: list[PernoiteFragMis]
    users: list[UserFragMis] = []
    etiquetas: list[EtiquetaSchema] = []
    custos: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class FragMisEmbed(FragMisSchema):
    """FragMis embarcado em comiss/financeiro — sem users, custo incluso."""

    # Herdado de FragMisSchema, mas omitido do payload financeiro: o item
    # de pagamento já expõe `user_mis`; a lista `users` seria redundante.
    users: list[UserFragMis] = Field(default=[], exclude=True)
    pernoites: list[PernoiteWithCusto] = []
    dias: int = 0
    diarias: float = 0
    valor_total: float = 0
    qtd_ac: int = 0
    # True quando o cache de custos não cobre o pg+sit lido (drift).
    custo_inconsistente: bool = False


class MissaoLogOut(BaseModel):
    id: int
    user: UserPublic
    action: str
    before: dict | None
    after: dict | None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class MissaoDetail(FragMisSchema):
    """FragMis com histórico de auditoria."""

    logs: list[MissaoLogOut] = []
    # True quando o cache de custos não reflete os inputs atuais da
    # missão (hash de integridade divergente — ver verificar_integridade).
    custo_inconsistente: bool = False
