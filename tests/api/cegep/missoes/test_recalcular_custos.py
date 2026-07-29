"""Testes de `recalcular_custos_missoes` (serviço de invalidação em lote).

Esta é a regra que liga as tabelas de referência (diárias/soldos) às
missões: quando um valor muda, todas as missões com pernoites no período
têm o cache `custos` recalculado, e os comissionamentos afetados
(militares sit='c') têm seu cache recalculado em seguida. Os testes
exercitam a propagação ponta-a-ponta contra o banco real.
"""

from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy import update

from fcontrol_api.models.cegep.diarias import DiariaValor
from fcontrol_api.models.shared.posto_grad import Soldo
from fcontrol_api.services.custos.integridade import chave_pg_sit
from fcontrol_api.services.missao import recalcular_custos_missoes
from tests.factories import (
    FragMisFactory,
    PernoiteFragFactory,
    UserFragFactory,
)

pytestmark = pytest.mark.anyio

# Campos de valor do cache do comissionamento. `updated_at` fica de fora
# de proposito: e carimbo de hora, muda a cada recalculo mesmo quando o
# resultado e identico.
CAMPOS_CACHE_COMISS = (
    'dias_comp',
    'diarias_comp',
    'vals_comp',
    'modulo',
    'completude',
    'missoes_count',
)


def _valores_cache(comiss) -> dict:
    cache = comiss.cache_calc or {}
    return {k: cache.get(k) for k in CAMPOS_CACHE_COMISS}


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


async def _missao_com_militar(
    session, *, n_doc, afast_date, regres_date, user, sit
):
    """Missão de um pernoite em SP com um único militar na situação dada."""
    missao = await _criar_missao(
        session, n_doc=n_doc, afast_date=afast_date, regres_date=regres_date
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
            frag_id=missao.id, user_id=user.id, sit=sit, p_g=user.p_g
        )
    )
    await session.commit()
    return missao


async def test_soldo_nao_altera_cache_do_comiss(session, user_with_comiss):
    """Mudar soldo NÃO muda o cache do comissionamento.

    Esta é a premissa que autoriza `afeta_comiss=False` no router de
    soldos: soldo só entra no cálculo de `sit='g'` (gratificação de
    representação, 2% do soldo/dia), e o cache do comissionamento lê
    exclusivamente a chave `pg_<p_g>_sit_c` do JSONB.

    O recálculo aqui roda com `afeta_comiss=True` de propósito — o ponto
    não é que ele foi pulado, e sim que rodá-lo é inócuo. Se algum dia o
    soldo passar a influenciar `sit='c'`, este teste quebra e o
    `afeta_comiss=False` do router precisa ser revisto.
    """
    user, comiss = user_with_comiss
    today = date.today()
    afast_date = today + timedelta(days=5)
    regres_date = today + timedelta(days=8)

    await _missao_com_militar(
        session,
        n_doc='7101',
        afast_date=afast_date,
        regres_date=regres_date,
        user=user,
        sit='c',
    )

    # Primeiro recálculo materializa o cache do comissionamento.
    await recalcular_custos_missoes(afast_date, regres_date, session)
    await session.refresh(comiss)
    antes = _valores_cache(comiss)
    assert antes['missoes_count'] >= 1  # o cenário tem custo de verdade

    # Dobra TODOS os soldos: o mais agressivo que uma edição de soldo
    # poderia ser.
    await session.execute(update(Soldo).values(valor=Soldo.valor * 2))
    await session.commit()

    resultado = await recalcular_custos_missoes(
        afast_date, regres_date, session, afeta_comiss=True
    )
    assert resultado['comissionamentos'] >= 1  # rodou de fato

    await session.refresh(comiss)
    assert _valores_cache(comiss) == antes


async def test_soldo_altera_custo_de_gratificacao(session, users):
    """Contraprova: soldo muda, sim, o custo de quem está em `sit='g'`.

    Sem esta asserção o teste acima seria vacuamente verdadeiro — passaria
    até se o recálculo estivesse quebrado e não mudasse nada em lugar
    nenhum.
    """
    user, _ = users
    today = date.today()
    afast_date = today + timedelta(days=5)
    regres_date = today + timedelta(days=8)

    missao = await _missao_com_militar(
        session,
        n_doc='7102',
        afast_date=afast_date,
        regres_date=regres_date,
        user=user,
        sit='g',
    )
    chave = chave_pg_sit(user.p_g, 'g')

    await recalcular_custos_missoes(afast_date, regres_date, session)
    await session.refresh(missao)
    antes = missao.custos['totais_pg_sit'][chave]['total_valor']
    assert antes > 0

    await session.execute(update(Soldo).values(valor=Soldo.valor * 2))
    await session.commit()

    await recalcular_custos_missoes(afast_date, regres_date, session)
    await session.refresh(missao)
    depois = missao.custos['totais_pg_sit'][chave]['total_valor']

    assert depois == pytest.approx(antes * 2)


async def test_diaria_altera_cache_do_comiss(session, user_with_comiss):
    """Contraste: diária muda o cache do comissionamento.

    É o que impede alguém de propagar o `afeta_comiss=False` do router de
    soldos para o de diárias "por simetria". Aqui o recálculo do segundo
    nível é obrigatório.
    """
    user, comiss = user_with_comiss
    today = date.today()
    afast_date = today + timedelta(days=5)
    regres_date = today + timedelta(days=8)

    await _missao_com_militar(
        session,
        n_doc='7103',
        afast_date=afast_date,
        regres_date=regres_date,
        user=user,
        sit='c',
    )

    await recalcular_custos_missoes(afast_date, regres_date, session)
    await session.refresh(comiss)
    antes = _valores_cache(comiss)
    assert antes['vals_comp'] > 0

    await session.execute(
        update(DiariaValor).values(valor=DiariaValor.valor * 2)
    )
    await session.commit()

    await recalcular_custos_missoes(afast_date, regres_date, session)
    await session.refresh(comiss)
    depois = _valores_cache(comiss)

    assert depois['vals_comp'] == pytest.approx(antes['vals_comp'] * 2)


async def test_afeta_comiss_false_recalcula_missao_sem_tocar_comiss(
    session, user_with_comiss
):
    """`afeta_comiss=False` pula só o segundo nível.

    O cache de custos da missão continua sendo recalculado; o do
    comissionamento é deixado intacto — inclusive quando ele estaria
    desatualizado (aqui, forçado por uma mudança de diária). É esse
    isolamento que torna a flag barata e previsível.
    """
    user, comiss = user_with_comiss
    today = date.today()
    afast_date = today + timedelta(days=5)
    regres_date = today + timedelta(days=8)

    missao = await _missao_com_militar(
        session,
        n_doc='7104',
        afast_date=afast_date,
        regres_date=regres_date,
        user=user,
        sit='c',
    )
    chave = chave_pg_sit(user.p_g, 'c')

    await recalcular_custos_missoes(afast_date, regres_date, session)
    await session.refresh(missao)
    await session.refresh(comiss)
    custo_missao_antes = missao.custos['totais_pg_sit'][chave]['total_valor']
    cache_comiss_antes = _valores_cache(comiss)

    await session.execute(
        update(DiariaValor).values(valor=DiariaValor.valor * 2)
    )
    await session.commit()

    resultado = await recalcular_custos_missoes(
        afast_date, regres_date, session, afeta_comiss=False
    )

    assert resultado['missoes'] >= 1
    assert resultado['comissionamentos'] == 0

    await session.refresh(missao)
    await session.refresh(comiss)

    # Missão: recalculada.
    custo_missao_depois = missao.custos['totais_pg_sit'][chave]['total_valor']
    assert custo_missao_depois == pytest.approx(custo_missao_antes * 2)

    # Comissionamento: intocado (ficou desatualizado de propósito).
    assert _valores_cache(comiss) == cache_comiss_antes
