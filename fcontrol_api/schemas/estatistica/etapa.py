from datetime import date, time
from typing import Annotated, Literal, Self

from fastapi import Body
from pydantic import BaseModel, ConfigDict, Field, model_validator


class EtapaBase(BaseModel):
    """Campos compartilhados entre entrada e saida."""

    data: date
    origem: str = Field(min_length=4, max_length=4)
    destino: str = Field(min_length=4, max_length=4)
    dep: time
    arr: time
    tvoo: int = Field(ge=5)
    anv: str = Field(max_length=4)
    pousos: int = Field(ge=0, le=32767)
    tow: int | None = Field(None, gt=0)
    pax: int | None = Field(None, ge=0, le=32767)
    carga: int | None = Field(None, ge=0, le=32767)
    comb: int | None = Field(None, gt=0, le=32767)
    lub: float | None = Field(None, ge=0, le=9999.9)
    nivel: str | None = Field(None, pattern=r'^\d{3}$')
    sagem: bool
    parte1: bool
    obs: str | None

    @model_validator(mode='after')
    def validate_tvoo(self) -> Self:
        """Valida consistencia de tvoo com dep/arr.

        Regra: a etapa nao pode atravessar o dia. arr DEVE ser
        > dep, com unica excecao: arr == 00:00 representa 24:00
        (fim do dia). Voos como 23:00->01:00 precisam ser
        divididos em 23:00->00:00 e 00:00->01:00.
        """
        dep_min = self.dep.hour * 60 + self.dep.minute
        arr_min = self.arr.hour * 60 + self.arr.minute
        # 00:00 no arr representa fim do dia (1440 min)
        if arr_min == 0 and dep_min > 0:
            arr_min = 1440
        if arr_min <= dep_min:
            msg = (
                'Etapa nao pode atravessar o dia. arr deve ser '
                'maior que dep (00:00 e aceito como fim do dia).'
            )
            raise ValueError(msg)
        expected = arr_min - dep_min
        if self.tvoo != expected:
            msg = (
                f'tvoo ({self.tvoo}) nao confere com dep/arr ({expected} min)'
            )
            raise ValueError(msg)
        return self


class EtapaOut(BaseModel):
    """Schema de saida para listagem de etapas."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    data: date
    origem: str
    destino: str
    dep: time
    arr: time
    tvoo: int
    anv: str
    pousos: int
    sagem: bool
    parte1: bool
    obs: str | None
    tripulantes: list['TripEtapaOut'] = []
    oi_etapas: list['OIEtapaOut'] = []
    pqd: list['PqdEtapaOut'] = []
    revo: list['RevoEtapaOut'] = []
    heavy_cds: list['HeavyCdsEtapaOut'] = []


class EtapaFlatOut(EtapaOut):
    """Schema de saida para listagem flat."""

    missao_id: int
    missao_titulo: str | None = None


class MissaoComEtapasOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    titulo: str | None
    obs: str | None
    is_simulador: bool = False
    etapas: list[EtapaOut]


class TripEtapaOut(BaseModel):
    """Tripulante vinculado a uma etapa."""

    trip_id: int
    trig: str
    nome_guerra: str
    p_g: str
    func: str
    func_bordo: str
    ant: int
    ult_promo: Annotated[date | None, Body()]
    ant_rel: int | None


class OIEtapaOut(BaseModel):
    """Ordem de Instrucao vinculada a uma etapa."""

    esf_aer_id: int
    tipo_missao_id: int
    esf_aer: str
    tipo_missao_cod: str
    reg: str
    tvoo: int


class PqdEtapaOut(BaseModel):
    """Lancamento de paraquedista vinculado a uma etapa."""

    model_config = ConfigDict(from_attributes=True)

    tipo: str
    qtd: int


class RevoEtapaOut(BaseModel):
    """Reabastecimento aereo vinculado a uma etapa."""

    model_config = ConfigDict(from_attributes=True)

    comb_transf: int


class HeavyCdsEtapaOut(BaseModel):
    """Lancamento de carga pesada (heavy/cds) vinculado a uma etapa."""

    model_config = ConfigDict(from_attributes=True)

    tipo: str
    peso: int
    dist: int
    radial: int


class EtapaDetailOut(EtapaOut):
    """Detalhe completo de uma etapa."""

    tow: int | None
    pax: int | None
    carga: int | None
    comb: int | None
    lub: float | None
    nivel: str | None


class MissaoComEtapasDetailOut(BaseModel):
    """Missao com etapas em detalhe completo (uso no editor)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    titulo: str | None
    obs: str | None
    is_simulador: bool = False
    etapas: list[EtapaDetailOut]


class TripEtapaIn(BaseModel):
    """Tripulante a vincular em uma etapa."""

    trip_id: int
    func: str
    func_bordo: str


_POSICOES_PILOTO = frozenset({'1P', '2P', 'IN', 'AL'})


def _check_pilot_duplicates(tripulantes) -> None:
    """Valida que nao ha posicoes de piloto duplicadas (1P, 2P, IN, AL)."""
    seen: set[str] = set()
    for t in tripulantes:
        if t.func_bordo in _POSICOES_PILOTO:
            if t.func_bordo in seen:
                msg = f'Posicao de piloto duplicada: {t.func_bordo}'
                raise ValueError(msg)
            seen.add(t.func_bordo)


class OIEtapaIn(BaseModel):
    """Ordem de Instrucao a vincular em uma etapa."""

    esf_aer_id: int
    tipo_missao_id: int
    reg: str = Field(pattern=r'^[dnv]$')
    tvoo: int = Field(gt=0, le=32767)


class PqdEtapaIn(BaseModel):
    """Lancamento de paraquedista a vincular em uma etapa."""

    tipo: Literal['VTC', 'LV', 'PREC', 'LIVRE']
    qtd: int = Field(ge=0, le=32767)


class RevoEtapaIn(BaseModel):
    """Reabastecimento aereo a vincular em uma etapa."""

    comb_transf: int = Field(ge=0, le=32767)


class HeavyCdsEtapaIn(BaseModel):
    """Lancamento de carga pesada a vincular em uma etapa."""

    tipo: Literal['heavy', 'cds']
    peso: int = Field(ge=0, le=32767)
    dist: int = Field(ge=0, le=32767)
    radial: int = Field(ge=0, lt=360)


class EtapaCreate(EtapaBase):
    """Schema de criacao de etapa com tripulantes."""

    # Missao.id e SMALLINT: fora do int16 estoura no asyncpg (500)
    missao_id: int = Field(gt=0, le=32767)
    tripulantes: list[TripEtapaIn] = []
    oi_etapas: list[OIEtapaIn] = []
    pqd: list[PqdEtapaIn] = []
    revo: list[RevoEtapaIn] = []
    heavy_cds: list[HeavyCdsEtapaIn] = []

    @model_validator(mode='after')
    def validate_pilot_duplicates(self) -> Self:
        if self.tripulantes:
            _check_pilot_duplicates(self.tripulantes)
        return self


class EtapaCreateNested(EtapaBase):
    """Etapa para criacao aninhada dentro de uma missao.

    Espelha EtapaCreate mas SEM missao_id — a etapa sera vinculada
    a missao criada na mesma transacao.

    Nota: tvoo e herdado de EtapaBase e validado contra dep/arr pelo
    model_validator. Embora o banco compute tvoo via trigger, o
    payload o exige para validar a consistencia das OIs antes de
    persistir.
    """

    tripulantes: list[TripEtapaIn] = []
    oi_etapas: list[OIEtapaIn] = []
    pqd: list[PqdEtapaIn] = []
    revo: list[RevoEtapaIn] = []
    heavy_cds: list[HeavyCdsEtapaIn] = []

    @model_validator(mode='after')
    def validate_pilot_duplicates(self) -> Self:
        if self.tripulantes:
            _check_pilot_duplicates(self.tripulantes)
        return self


def _check_oi_sums(items, label: str) -> None:
    """Valida sum(oi.tvoo) == etapa.tvoo para cada item.

    Late-bound: usado pelos validadores de MissaoComEtapasCreate
    e MissaoComEtapasUpdate. Levanta ValueError descritivo com
    o indice + label do payload em conflito.
    """
    for idx, etapa in enumerate(items):
        if not etapa.oi_etapas:
            continue
        soma = sum(oi.tvoo for oi in etapa.oi_etapas)
        if soma != etapa.tvoo:
            msg = (
                f'{label}[{idx}]: soma das OIs ({soma}) '
                f'nao confere com tvoo ({etapa.tvoo})'
            )
            raise ValueError(msg)


class MissaoComEtapasCreate(BaseModel):
    """Payload atomico: cria missao + etapas em uma transacao."""

    titulo: str | None = None
    obs: str | None = None
    is_simulador: bool = False
    etapas: list[EtapaCreateNested] = Field(min_length=1)

    @model_validator(mode='after')
    def validate_oi_sums(self) -> Self:
        """Valida soma OIs == tvoo para cada etapa do payload."""
        _check_oi_sums(self.etapas, 'etapa')
        return self


class EtapaUpdateNested(EtapaBase):
    """Etapa existente a ser atualizada dentro de uma missao.

    Espelha EtapaCreateNested mas com `id` obrigatorio. Usado no
    endpoint atomico PUT /missao/{id}/with-etapas. Semantica de
    "full replace": o cliente DEVE enviar todos os campos (e a
    lista completa de OIs/tripulantes — o servidor descarta as
    associacoes anteriores e regrava com o conteudo recebido).
    """

    id: int
    tripulantes: list[TripEtapaIn] = []
    oi_etapas: list[OIEtapaIn] = []
    pqd: list[PqdEtapaIn] = []
    revo: list[RevoEtapaIn] = []
    heavy_cds: list[HeavyCdsEtapaIn] = []

    @model_validator(mode='after')
    def validate_pilot_duplicates(self) -> Self:
        if self.tripulantes:
            _check_pilot_duplicates(self.tripulantes)
        return self


class MissaoComEtapasUpdate(BaseModel):
    """Payload atomico: atualiza missao + etapas em uma transacao.

    `delete_ids` lista etapas a remover. `update` traz etapas
    existentes com novos valores (replace de OIs/tripulantes).
    `create` insere novas etapas vinculadas a esta missao.
    `is_simulador` e imutavel apos a criacao — nao e aceito aqui.
    """

    titulo: str | None = None
    obs: str | None = None
    delete_ids: list[int] = Field(default_factory=list)
    update: list[EtapaUpdateNested] = Field(default_factory=list)
    create: list[EtapaCreateNested] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_payload(self) -> Self:
        """Valida unicidade, sem-interseccao e somas de OI."""
        update_ids = [e.id for e in self.update]
        if len(update_ids) != len(set(update_ids)):
            dupes = sorted({i for i in update_ids if update_ids.count(i) > 1})
            msg = f'IDs duplicados em update: {dupes}'
            raise ValueError(msg)
        overlap = set(update_ids) & set(self.delete_ids)
        if overlap:
            msg = (
                f'IDs nao podem aparecer em update e '
                f'delete_ids ao mesmo tempo: {sorted(overlap)}'
            )
            raise ValueError(msg)
        _check_oi_sums(self.create, 'create')
        _check_oi_sums(self.update, 'update')
        return self


class EtapaUpdate(BaseModel):
    """Schema de atualizacao (campos opcionais)."""

    data: date | None = None
    origem: str | None = Field(None, min_length=4, max_length=4)
    destino: str | None = Field(None, min_length=4, max_length=4)
    dep: time | None = None
    arr: time | None = None
    tvoo: int | None = Field(None, ge=5)
    anv: str | None = Field(None, max_length=4)
    pousos: int | None = Field(None, ge=0, le=32767)
    tow: int | None = Field(None, gt=0)
    pax: int | None = Field(None, ge=0, le=32767)
    carga: int | None = Field(None, ge=0, le=32767)
    comb: int | None = Field(None, gt=0, le=32767)
    lub: float | None = Field(None, ge=0, le=9999.9)
    nivel: str | None = Field(None, pattern=r'^\d{3}$')
    sagem: bool | None = None
    parte1: bool | None = None
    obs: str | None = None
    tripulantes: list[TripEtapaIn] | None = None
    oi_etapas: list[OIEtapaIn] | None = None
    pqd: list[PqdEtapaIn] | None = None
    revo: list[RevoEtapaIn] | None = None
    heavy_cds: list[HeavyCdsEtapaIn] | None = None

    @model_validator(mode='after')
    def validate_pilot_duplicates(self) -> Self:
        if self.tripulantes:
            _check_pilot_duplicates(self.tripulantes)
        return self


class EtapaPublic(BaseModel):
    """Schema de resposta apos criar/atualizar."""

    model_config = ConfigDict(from_attributes=True)

    id: int


class EtapaExportRequest(BaseModel):
    """Requisicao de exportacao de etapas para Excel."""

    ids: list[int] = Field(min_length=1)
    pousos: bool = False
    nivel: bool = False
    tow: bool = False
    pax: bool = False
    carga: bool = False
    comb: bool = False
    lub: bool = False
    esforco_aereo: bool = False
    tripulantes: bool = False


class MissaoCreate(BaseModel):
    titulo: str | None = None
    obs: str | None = None
    is_simulador: bool = False


class MissaoUpdate(BaseModel):
    titulo: str | None = None
    obs: str | None = None


class MissaoPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    titulo: str | None
    obs: str | None
    is_simulador: bool = False
