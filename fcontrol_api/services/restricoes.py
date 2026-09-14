from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.models.shared.operacao import Operacao, OperacaoPessoal
from fcontrol_api.schemas.restricoes import RestricaoDerivada

DIAS_PARA_DESADAPTACAO = 45
FUNCOES_ISENTAS_DESADAPTACAO = frozenset({'oe', 'os'})

# Operação cancelada não tira ninguém da unidade; planejada, em andamento e
# encerrada tiram (a encerrada porque o período já passou e a grade também
# olha para trás).
STATUS_OPERACAO_INDISPONIBILIZA = frozenset({
    'planejada',
    'andamento',
    'encerrada',
})


@dataclass(frozen=True)
class PeriodoOperacao:
    """Um período de um militar numa operação, já resolvido pelo chamador.

    A camada de rota é que sabe consultar `operacao_pessoal`; aqui entra só o
    que a regra precisa, para a função continuar pura e testável sem banco.
    """

    operacao_id: int
    nome: str
    status: str
    data_ingresso: date
    data_regresso: date


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


def restricoes_de_operacao(
    periodos: list[PeriodoOperacao],
) -> list[RestricaoDerivada]:
    """Projeta uma restrição por período de operação do militar.

    Uma por período, e não uma por operação: quem sai no meio e volta depois
    tem dois intervalos, e fundi-los afirmaria que ele esteve fora também nos
    dias em que voltou (ver `OperacaoPessoal`).

    É bloqueio, não aviso — no período o militar está fisicamente fora da
    unidade, então escalá-lo é erro, não risco a ponderar.
    """
    return [
        RestricaoDerivada(
            origem='operacao',
            codigo='operacao',
            inicio=p.data_ingresso,
            fim=p.data_regresso,
            efeito='bloqueio',
            rotulo=p.nome,
            operacao_id=p.operacao_id,
        )
        for p in periodos
        if p.status in STATUS_OPERACAO_INDISPONIBILIZA
    ]


async def buscar_periodos_operacao(
    session: AsyncSession,
    user_ids: Sequence[int],
    date_from: date,
    date_to: date | None,
    active_org: str,
) -> dict[int, list[PeriodoOperacao]]:
    """Períodos de operação que cruzam a janela, agrupados por `user_id`.

    Vive aqui, e não em cada rota, porque a grade e a escala fazem a mesma
    pergunta — duas cópias divergiriam na primeira mudança de regra.

    O escopo por `uae` é obrigatório aqui: os chamadores filtram a org no
    TRIPULANTE, mas o `user_id` que sai dali é global, e `add_pessoal` valida a
    operação pela org sem validar o militar. Sem este filtro, um militar
    emprestado a outra unidade traria para esta grade o nome de uma operação
    alheia — com um deeplink que cai no 404 de `_get_op`.
    """
    if not user_ids:
        return {}

    filtros = [
        OperacaoPessoal.user_id.in_(user_ids),
        OperacaoPessoal.data_regresso >= date_from,
        Operacao.status.in_(STATUS_OPERACAO_INDISPONIBILIZA),
        Operacao.uae == active_org,
    ]
    if date_to is not None:
        filtros.append(OperacaoPessoal.data_ingresso <= date_to)

    query = (
        select(
            OperacaoPessoal.user_id,
            OperacaoPessoal.data_ingresso,
            OperacaoPessoal.data_regresso,
            Operacao.id,
            Operacao.nome,
            Operacao.status,
        )
        .join(Operacao, Operacao.id == OperacaoPessoal.operacao_id)
        .where(*filtros)
        .order_by(OperacaoPessoal.data_ingresso)
    )

    por_user: dict[int, list[PeriodoOperacao]] = defaultdict(list)
    for row in (await session.execute(query)).all():
        por_user[row.user_id].append(
            PeriodoOperacao(
                operacao_id=row.id,
                nome=row.nome,
                status=row.status,
                data_ingresso=row.data_ingresso,
                data_regresso=row.data_regresso,
            )
        )
    return por_user
