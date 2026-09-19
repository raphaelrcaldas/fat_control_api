"""Cálculo da Gratificação de Localidade Especial Eventual (GLE).

Regra do Decreto 4.307/2002, alterado pelo Decreto 11.020/2022, conforme a
planilha GLEE que esta calculadora substitui:

    valor = multiplicador x soldo_do_posto
    multiplicador = SOMA (1 / dias_do_mes(dia)) x fator_categoria

O dia é **proporcional ao mês em que cai**: um dia de fevereiro vale 1/28 e
um de janeiro 1/31, então um período que atravessa meses soma frações de
denominadores diferentes. O fator vem da categoria da localidade — A = 20%
do soldo, B = 10%.

Nem todo dia do período conta: vale o critério das 8 horas, em
`dias_contaveis`.
"""

from calendar import monthrange
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

# Fator por categoria: A = 20% do soldo, B = 10%. As chaves são os mesmos
# inteiros de `GrupoLocEsp.grupo` (1 = A, 2 = B).
FATOR_CATEGORIA: dict[int, Decimal] = {
    1: Decimal('0.20'),
    2: Decimal('0.10'),
}

# Um dia só conta se a permanência nele alcançar 8 horas.
HORAS_MINIMAS = 8


def _horas(inicio: datetime, fim: datetime) -> Decimal:
    return Decimal((fim - inicio).total_seconds()) / Decimal(3600)


def _meia_noite_seguinte(momento: datetime) -> datetime:
    return datetime.combine(momento.date() + timedelta(days=1), time.min)


def dias_contaveis(
    chegada: datetime, afastamento: datetime
) -> list[tuple[date, Decimal]]:
    """Dias que geram gratificação, com as horas de permanência em cada um.

    O critério das 8 horas se aplica só às **pontas**; dia intermediário é
    integral. Quando ida e volta caem no mesmo dia, há uma ponta só, e o
    que vale é a duração total da permanência.
    """
    if afastamento <= chegada:
        return []

    dia_ini, dia_fim = chegada.date(), afastamento.date()

    if dia_ini == dia_fim:
        horas = _horas(chegada, afastamento)
        return [(dia_ini, horas)] if horas >= HORAS_MINIMAS else []

    dias: list[tuple[date, Decimal]] = []

    # Chegada: conta se sobram 8h até a meia-noite.
    horas_chegada = _horas(chegada, _meia_noite_seguinte(chegada))
    if horas_chegada >= HORAS_MINIMAS:
        dias.append((dia_ini, horas_chegada))

    # Intermediários: integrais, sem teste de horas.
    dia = dia_ini + timedelta(days=1)
    while dia < dia_fim:
        dias.append((dia, Decimal(24)))
        dia += timedelta(days=1)

    # Afastamento: conta se já se passaram 8h desde a meia-noite.
    horas_saida = _horas(datetime.combine(dia_fim, time.min), afastamento)
    if horas_saida >= HORAS_MINIMAS:
        dias.append((dia_fim, horas_saida))

    return dias


def fator_do_dia(dia: date, grupo: int) -> Decimal:
    """Fração de soldo que um dia gera: (1 / dias do mês) x fator."""
    dias_no_mes = monthrange(dia.year, dia.month)[1]
    return Decimal(1) / Decimal(dias_no_mes) * FATOR_CATEGORIA[grupo]


def resolver_sobreposicao(
    trechos: list[list[tuple[date, Decimal]]],
) -> list[dict[date, Decimal]]:
    """Impede que o mesmo dia seja pago duas vezes.

    Quando o militar sai de uma localidade e chega em outra no mesmo dia,
    esse dia aparece em dois trechos. Paga-se **o de maior valor** e zera-se
    o outro — regra herdada da planilha.

    Recebe, por trecho, os pares (dia, fator já calculado); devolve, por
    trecho, o mapa dia -> fator com os duplicados zerados.
    """
    vencedor: dict[date, tuple[int, Decimal]] = {}
    for indice, dias in enumerate(trechos):
        for dia, fator in dias:
            atual = vencedor.get(dia)
            # `>` e não `>=`: empate mantém o primeiro trecho, que é o mais
            # antigo — determinístico e igual ao da planilha.
            if atual is None or fator > atual[1]:
                vencedor[dia] = (indice, fator)

    resultado: list[dict[date, Decimal]] = []
    for indice, dias in enumerate(trechos):
        mapa: dict[date, Decimal] = {}
        for dia, fator in dias:
            ganhou = vencedor[dia][0] == indice
            mapa[dia] = fator if ganhou else Decimal(0)
        resultado.append(mapa)
    return resultado


CENTAVO = Decimal('0.01')

# O multiplicador é uma soma de dízimas (1/30, 1/31...). Guardamos 8 casas
# para exibir e transportar: o suficiente para reproduzir o centavo e não
# vazar uma cauda de 28 dígitos na resposta. A conta interna continua na
# precisão cheia do Decimal — só a apresentação é arredondada.
CASAS_MULTIPLICADOR = Decimal('0.00000001')


def quantizar_multiplicador(valor: Decimal) -> Decimal:
    # `normalize()` no zero devolveria "0E-8" na serialização JSON, que o
    # front exibiria cru. O zero volta como Decimal(0) limpo.
    quantizado = valor.quantize(CASAS_MULTIPLICADOR, rounding=ROUND_HALF_UP)
    return Decimal(0) if quantizado == 0 else quantizado


def quantizar(valor: Decimal) -> Decimal:
    """Arredonda a centavos (ROUND_HALF_UP, padrão BRL)."""
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def soldo_do_dia(pg: str, dia: date, cache: dict) -> Decimal:
    """Soldo vigente do posto naquele dia.

    `Soldo` é datado e a `ExcludeConstraint` garante que as vigências não se
    sobrepõem, então no máximo uma faixa casa. Um reajuste no meio do
    período é aplicado a partir do dia em que passa a valer — daí o cálculo
    ser dia a dia, e não `soldo_atual x multiplicador`.

    Espelha `_buscar_soldo_por_dia` de `services/custos/calculo.py`, que é
    privado daquele módulo; o cache (`cache_soldos`) é o mesmo.
    """
    for item in cache.get(pg, []):
        if item.data_inicio <= dia and (
            item.data_fim is None or dia <= item.data_fim
        ):
            return item.valor
    return Decimal(0)
