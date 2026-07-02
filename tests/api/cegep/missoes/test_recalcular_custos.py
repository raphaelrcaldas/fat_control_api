"""Testes de `recalcular_custos_missoes` (serviço de invalidação em lote).

Esta é a regra que liga as tabelas de referência (diárias/soldos) às
missões: quando um valor muda, todas as missões com pernoites no período
têm o cache `custos` recalculado, e os comissionamentos afetados
(militares sit='c') têm seu cache recalculado em seguida. Os testes
exercitam a propagação ponta-a-ponta contra o banco real.
"""

from datetime import date, datetime, time, timedelta

import pytest

from fcontrol_api.services.missao import recalcular_custos_missoes
from tests.factories import (
    FragMisFactory,
    PernoiteFragFactory,
    UserFragFactory,
)

pytestmark = pytest.mark.anyio


async def _criar_missao(session, *, n_doc, afast_date, regres_date):
    missao = FragMisFactory(
        n_doc=n_doc,
        tipo_doc='om',
        tipo='adm',
        acrec_desloc=False,
        indenizavel=True,
        afast=datetime.combine(afast_date, time(8, 0)),
        regres=datetime.combine(regres_date, time(18, 0)),
    )
    session.add(missao)
    await session.flush()
    return missao


async def test_recalcular_atualiza_custos_e_comiss(session, user_with_comiss):
    """sit='c' dentro do comiss: recalcula custos da missão E do comiss.

    Cobre o caminho completo do laço (incluindo o recálculo de
    comissionamentos afetados).
    """
    user, comiss = user_with_comiss
    today = date.today()
    afast_date = today + timedelta(days=5)
    regres_date = today + timedelta(days=8)

    missao = await _criar_missao(
        session, n_doc='7001', afast_date=afast_date, regres_date=regres_date
    )
    session.add(
        PernoiteFragFactory(
            frag_id=missao.id,
            cidade_id=3550308,
            data_ini=afast_date,
            data_fim=regres_date,
            acrec_desloc=False,
            meia_diaria=False,
            obs='',
        )
    )
    session.add(
        UserFragFactory(
            frag_id=missao.id, user_id=user.id, sit='c', p_g=user.p_g
        )
    )
    await session.commit()

    resultado = await recalcular_custos_missoes(
        afast_date, regres_date, session
    )

    assert resultado['missoes'] >= 1
    assert resultado['comissionamentos'] >= 1

    await session.refresh(missao)
    assert missao.custos  # cache materializado
    assert missao.custos['total_dias'] >= 1

    await session.refresh(comiss)
    assert comiss.cache_calc is not None


async def test_recalcular_ignora_missao_sem_militares(session):
    """Missão com pernoite no período mas SEM militares é pulada.

    Sem militares não há custo a materializar: `custos` permanece vazio
    e a missão não entra na contagem de processadas com sucesso.
    """
    today = date.today()
    afast_date = today + timedelta(days=40)
    regres_date = today + timedelta(days=43)

    missao = await _criar_missao(
        session, n_doc='7002', afast_date=afast_date, regres_date=regres_date
    )
    session.add(
        PernoiteFragFactory(
            frag_id=missao.id,
            cidade_id=3550308,
            data_ini=afast_date,
            data_fim=regres_date,
            acrec_desloc=False,
            meia_diaria=False,
            obs='',
        )
    )
    await session.commit()

    resultado = await recalcular_custos_missoes(
        afast_date, regres_date, session
    )

    # A missão é encontrada pela query (tem pernoite), mas pulada por não
    # ter militares -> nenhum comissionamento afetado.
    assert resultado['comissionamentos'] == 0

    await session.refresh(missao)
    assert not missao.custos


async def test_recalcular_sem_missoes_no_periodo(session):
    """Período sem missões: retorna contagens zeradas (sem efeito)."""
    longe = date(2000, 1, 1)
    resultado = await recalcular_custos_missoes(longe, longe, session)

    assert resultado == {'missoes': 0, 'comissionamentos': 0}


async def test_recalcular_periodo_aberto_sem_data_fim(
    session, user_with_comiss
):
    """data_fim=None: recalcula todas as missões a partir de data_inicio."""
    user, _ = user_with_comiss
    today = date.today()
    afast_date = today + timedelta(days=5)
    regres_date = today + timedelta(days=7)

    missao = await _criar_missao(
        session, n_doc='7003', afast_date=afast_date, regres_date=regres_date
    )
    session.add(
        PernoiteFragFactory(
            frag_id=missao.id,
            cidade_id=3550308,
            data_ini=afast_date,
            data_fim=regres_date,
            acrec_desloc=False,
            meia_diaria=False,
            obs='',
        )
    )
    session.add(
        UserFragFactory(
            frag_id=missao.id, user_id=user.id, sit='d', p_g=user.p_g
        )
    )
    await session.commit()

    resultado = await recalcular_custos_missoes(afast_date, None, session)

    assert resultado['missoes'] >= 1
    await session.refresh(missao)
    assert missao.custos
