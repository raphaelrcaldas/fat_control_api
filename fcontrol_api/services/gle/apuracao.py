"""Apura os trechos de uma missão com o soldo vigente em cada dia.

O posto recebido é o snapshot salvo na missão. O resultado é recalculado
na leitura, sem persistir valores derivados.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.models.shared.estados_cidades import Cidade, GrupoLocEsp
from fcontrol_api.schemas.cegep.gle_calculo import (
    DiaCalculado,
    TrechoCalculado,
)
from fcontrol_api.services.custos.cache_ref import cache_soldos
from fcontrol_api.services.gle.calculo import (
    dias_contaveis,
    fator_do_dia,
    quantizar,
    quantizar_multiplicador,
    resolver_sobreposicao,
    soldo_do_dia,
)

ROTULO_PERCENTUAL = {1: '20%', 2: '10%'}


@dataclass(frozen=True)
class TrechoApurar:
    loc_esp_id: int
    chegada: datetime
    afastamento: datetime


@dataclass(frozen=True)
class MilitarApurar:
    """Militar a apurar.

    `p_g` vem de fora porque a missão salva guarda o **snapshot** do posto:
    promover alguém não pode reescrever uma apuração já feita.
    """

    user_id: int
    p_g: str
    nome_guerra: str
    nome_completo: str | None
    saram: str


@dataclass
class Apuracao:
    multiplicador: Decimal
    percentual: str
    trechos: list[TrechoCalculado]
    # (user_id, soldo_de_referência, valor) por militar, na ordem recebida.
    valores: list[tuple[int, Decimal, Decimal]]


async def apurar(
    session: AsyncSession,
    trechos: list[TrechoApurar],
    militares: list[MilitarApurar],
    por_id: dict[int, tuple[GrupoLocEsp, Cidade]],
) -> Apuracao:
    """Calcula o multiplicador, a memória por dia e o valor de cada militar.

    `por_id` entra pronto para quem chama validar antes o que falta e
    devolver o erro na linguagem do seu endpoint.
    """
    # Fator de cada dia de cada trecho, antes da antisobreposição.
    dias_por_trecho: list[list[tuple[date, Decimal]]] = []
    horas_por_trecho: list[dict[date, Decimal]] = []
    for trecho in trechos:
        loc, _ = por_id[trecho.loc_esp_id]
        dias = dias_contaveis(trecho.chegada, trecho.afastamento)
        horas_por_trecho.append(dict(dias))
        dias_por_trecho.append([
            (dia, fator_do_dia(dia, loc.grupo)) for dia, _ in dias
        ])

    resolvidos = resolver_sobreposicao(dias_por_trecho)

    trechos_out: list[TrechoCalculado] = []
    multiplicador = Decimal(0)
    for trecho, fatores, horas in zip(trechos, resolvidos, horas_por_trecho):
        loc, cidade = por_id[trecho.loc_esp_id]
        subtotal = sum(fatores.values(), Decimal(0))
        multiplicador += subtotal
        trechos_out.append(
            TrechoCalculado(
                loc_esp_id=loc.id,
                cidade=cidade.nome,
                uf=cidade.uf,
                grupo=loc.grupo,
                chegada=trecho.chegada,
                afastamento=trecho.afastamento,
                # Dia zerado pela antisobreposição não é dia pago: ele
                # aparece na memória, mas não conta aqui.
                dias_contados=sum(1 for f in fatores.values() if f != 0),
                multiplicador=quantizar_multiplicador(subtotal),
                dias=[
                    DiaCalculado(
                        data=dia,
                        horas=horas[dia],
                        fator=quantizar_multiplicador(fator),
                        duplicado=fator == 0,
                    )
                    for dia, fator in sorted(fatores.items())
                ],
            )
        )

    soldos_cache = await cache_soldos(session)

    # O valor usa o soldo vigente em cada dia, mas a resposta mantém como
    # referência o soldo do primeiro dia pago entre todos os trechos. O
    # mínimo explícito evita depender da ordem em que eles foram enviados.
    # Havendo reajuste, `soldo * multiplicador` não reproduz `valor`: as
    # parcelas foram calculadas com vigências diferentes, de propósito.
    primeiro_dia_pago = min(
        (
            dia
            for fatores in resolvidos
            for dia, fator in fatores.items()
            if fator != 0
        ),
        default=None,
    )

    valores: list[tuple[int, Decimal, Decimal]] = []
    for militar in militares:
        valor = Decimal(0)
        soldo_ref = (
            soldo_do_dia(militar.p_g, primeiro_dia_pago, soldos_cache)
            if primeiro_dia_pago is not None
            else Decimal(0)
        )
        for fatores in resolvidos:
            for dia, fator in fatores.items():
                if fator == 0:
                    continue
                soldo_dia = soldo_do_dia(militar.p_g, dia, soldos_cache)
                valor += fator * soldo_dia
        valores.append((militar.user_id, soldo_ref, quantizar(valor)))

    grupos = {por_id[t.loc_esp_id][0].grupo for t in trechos}
    percentual = ' e '.join(ROTULO_PERCENTUAL[g] for g in sorted(grupos))

    return Apuracao(
        multiplicador=quantizar_multiplicador(multiplicador),
        percentual=percentual,
        trechos=trechos_out,
        valores=valores,
    )
