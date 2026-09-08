from datetime import date, timedelta

from fcontrol_api.schemas.restricoes import RestricaoDerivada

DIAS_PARA_DESADAPTACAO = 45
FUNCOES_ISENTAS_DESADAPTACAO = frozenset({'oe', 'os'})


def elegivel_desadaptacao(
    *, funcao: str, operacionalidade: str | None
) -> bool:
    """Indica se a função está sujeita à regra de recência."""
    return (
        funcao not in FUNCOES_ISENTAS_DESADAPTACAO and operacionalidade != 'al'
    )


def calcular_restricoes_derivadas(
    *,
    cemal: date | None,
    ultimo_voo: date | None,
    funcao: str,
    operacionalidade: str | None,
) -> list[RestricaoDerivada]:
    """Projeta restrições das fontes atuais, sem reconstruir histórico."""
    restricoes: list[RestricaoDerivada] = []

    if cemal is None:
        restricoes.append(
            RestricaoDerivada(
                origem='cemal',
                codigo='cemal_ausente',
                inicio=None,
                fim=None,
                efeito='bloqueio',
            )
        )
    elif cemal < date.max:
        restricoes.append(
            RestricaoDerivada(
                origem='cemal',
                codigo='cemal_vencido',
                inicio=cemal + timedelta(days=1),
                fim=None,
                efeito='bloqueio',
            )
        )

    sujeito_recencia = elegivel_desadaptacao(
        funcao=funcao, operacionalidade=operacionalidade
    )
    limite_ultimo_voo = date.max - timedelta(days=DIAS_PARA_DESADAPTACAO)
    if (
        ultimo_voo is not None
        and ultimo_voo <= limite_ultimo_voo
        and sujeito_recencia
    ):
        restricoes.append(
            RestricaoDerivada(
                origem='recencia_voo',
                codigo='desadaptacao',
                inicio=ultimo_voo + timedelta(days=DIAS_PARA_DESADAPTACAO),
                fim=None,
                efeito='aviso',
            )
        )

    return restricoes
