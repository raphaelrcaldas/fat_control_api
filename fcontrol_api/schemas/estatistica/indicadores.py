from decimal import Decimal

from pydantic import BaseModel, field_serializer


class Metricas(BaseModel):
    """Bloco de metricas agregadas de um recorte de etapas.

    Unidades: `tvoo` em minutos, `carga` e `peso_lancado` em kg,
    `comb`/`comb_transf` e `lub` em litros.

    Lancamentos em branco (procedimento simulado, nada largado) nao
    entram em `heavy_qtd`/`cds_qtd` e somam zero em `pqd` e
    `peso_lancado`. Eles seguem contando como etapa voada.
    """

    etapas: int
    tvoo: int
    pousos: int
    pax: int
    carga: int
    comb: int
    lub: Decimal
    pqd: int
    comb_transf: int
    heavy_qtd: int
    cds_qtd: int
    peso_lancado: int

    @field_serializer('lub')
    def serialize_lub(self, v: Decimal) -> float:
        return float(v)


class MesLinha(Metricas):
    """Uma coluna da matriz mensal. Sempre 12 por ano, zeros inclusos."""

    mes: int


class RegimeLinha(BaseModel):
    """Horas por regime de voo (d=diurno, n=noturno, v=NVG).

    Vem de `OIEtapa.tvoo`, que ja e rateado por construcao: somar
    carga/pax/comb agrupando por OI multiplicaria a etapa.
    """

    reg: str
    tvoo: int


class TipoMissaoLinha(BaseModel):
    """Horas por tipo de missao. Mesma restricao de `RegimeLinha`."""

    cod: str
    desc: str
    tvoo: int
    etapas: int


class AeronaveLinha(BaseModel):
    """Producao por aeronave no ano."""

    anv: str
    projeto: str
    etapas: int
    tvoo: int
    pousos: int
    carga: int
    pax: int


class PqdTipoLinha(BaseModel):
    """Paraquedistas lancados por tipo (VTC, LV, PREC, LIVRE).

    Tipo que so teve lancamento em branco no recorte nao aparece.
    """

    tipo: str
    qtd: int


class LancamentoLinha(BaseModel):
    """Cargas lancadas por tipo (heavy, cds): quantidade e peso em kg.

    Lancamento em branco (`peso = 0`) nao entra em `qtd`; tipo que so
    teve branco no recorte nao aparece.
    """

    tipo: str
    qtd: int
    peso: int


class IndicadoresResponse(BaseModel):
    """Painel anual de indicadores das etapas voadas."""

    ano_ref: int
    totais: Metricas
    mensal: list[MesLinha]
    por_regime: list[RegimeLinha]
    por_tipo_missao: list[TipoMissaoLinha]
    por_aeronave: list[AeronaveLinha]
    pqd_por_tipo: list[PqdTipoLinha]
    lancamentos: list[LancamentoLinha]
