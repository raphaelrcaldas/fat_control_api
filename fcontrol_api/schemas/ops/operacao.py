"""Schemas do módulo Operações / Manobras / Exercícios."""

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fcontrol_api.schemas.users import UserPublic

OperTipo = Literal['operacao', 'manobra', 'exercicio']
OperStatus = Literal['planejada', 'andamento', 'encerrada', 'cancelada']


# --------------------------------------------------------------------------- #
# Entrada
# --------------------------------------------------------------------------- #
class OperacaoCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    tipo: OperTipo
    cidade_id: int
    data_inicio: date
    data_fim: date
    status: OperStatus = 'planejada'
    documento_diretriz: str | None = Field(default=None, max_length=100)
    obs: str | None = None

    @model_validator(mode='after')
    def _periodo(self) -> 'OperacaoCreate':
        if self.data_fim < self.data_inicio:
            raise ValueError('data_fim deve ser maior ou igual a data_inicio')
        return self


class OperacaoUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    tipo: OperTipo | None = None
    cidade_id: int | None = None
    data_inicio: date | None = None
    data_fim: date | None = None
    status: OperStatus | None = None
    documento_diretriz: str | None = None
    obs: str | None = None


class AssociarEtapas(BaseModel):
    etapa_ids: list[int] = Field(min_length=1)


class OperacaoPessoalIn(BaseModel):
    user_id: int
    func: str = Field(min_length=1, max_length=80)
    om: str = Field(min_length=1, max_length=60)
    data_ingresso: date
    data_regresso: date

    @model_validator(mode='after')
    def _periodo(self) -> 'OperacaoPessoalIn':
        if self.data_regresso < self.data_ingresso:
            raise ValueError(
                'data_regresso deve ser maior ou igual a data_ingresso'
            )
        return self


# --------------------------------------------------------------------------- #
# Saída
# --------------------------------------------------------------------------- #
class CidadeMini(BaseModel):
    codigo: int
    nome: str
    uf: str

    model_config = ConfigDict(from_attributes=True)


class OperacaoListItem(BaseModel):
    """Linha-card da lista de operações (com agregados de voo)."""

    id: int
    numero: int
    nome: str
    tipo: str
    status: str
    documento_diretriz: str | None
    cidade: CidadeMini | None
    data_inicio: date
    data_fim: date
    dias: int
    horas: int  # Σ tvoo em minutos (frontend formata HH:MM)
    etapas: int
    anv: int


class OperacaoTabCounts(BaseModel):
    todas: int
    andamento: int
    encerrada: int
    planejada: int
    cancelada: int


class OperacaoListResponse(BaseModel):
    items: list[OperacaoListItem]
    counts: OperacaoTabCounts


class OperacaoKpis(BaseModel):
    horas: int  # Σ tvoo (min)
    etapas: int
    anv: int  # matrículas distintas
    pax: int
    carga: int  # kg
    comb: int  # L
    missoes: int  # missões distintas
    modelos: int  # modelos de aeronave distintos


class EsforcoRow(BaseModel):
    esf_aer_id: int
    descricao: str
    etapas: int
    horas: int  # Σ OIEtapa.tvoo (min)


class EsforcoBloco(BaseModel):
    rows: list[EsforcoRow]
    total_etapas: int
    total_horas: int


class SeboRow(BaseModel):
    trip_id: int
    nome: str
    func: str  # função predominante (PIL/COP/MEC/LOA/CMG)
    etapas: int
    horas: int  # Σ tvoo (min)


class OperacaoDetail(BaseModel):
    id: int
    numero: int
    nome: str
    tipo: str
    status: str
    documento_diretriz: str | None
    cidade: CidadeMini | None
    data_inicio: date
    data_fim: date
    dias: int
    obs: str | None
    created_at: datetime
    kpis: OperacaoKpis
    esforco: EsforcoBloco
    sebo: list[SeboRow]


class EtapaTripMini(BaseModel):
    nome: str
    func: str


class OperacaoEtapaRow(BaseModel):
    """Etapa associada (linha da tabela + dados do drawer)."""

    id: int
    data: date
    origem: str
    destino: str
    anv: str
    modelo: str | None
    esforco: str | None  # descrição(ões) de esforço aéreo
    missao_id: int
    tvoo: int
    dep: time
    arr: time
    nivel: str | None
    pousos: int
    pax: int | None
    carga: int | None
    comb: int | None
    trip: list[EtapaTripMini]


class EtapaCandidata(BaseModel):
    id: int
    data: date
    origem: str
    destino: str
    anv: str
    missao_id: int
    tvoo: int
    bloqueada: bool  # já vinculada a outra operação (1:N)
    operacao_atual: int | None


class OperacaoPessoalOut(BaseModel):
    id: int
    user: UserPublic
    func: str
    om: str
    data_ingresso: date
    data_regresso: date
    dias: int
