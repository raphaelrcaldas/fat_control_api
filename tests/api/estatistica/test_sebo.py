"""Pau de Sebo — GET /estatistica/sebo/.

É um ranking de horas voadas REAIS: o que define simulador é a missão
(`Missao.is_simulador`), não a aeronave nem a linha de esforço. Uma sessão
de simulador não soma horas, não conta como último voo (DSV) e não sobe
ninguém no ranking.
"""

from datetime import date, time
from http import HTTPStatus

import pytest
from sqlalchemy import func, select

from fcontrol_api.models.estatistica.etapa import Etapa, Missao, TripEtapa
from fcontrol_api.models.shared.aeronaves import Aeronave
from tests.factories import TripFactory, UserFactory

pytestmark = pytest.mark.anyio

URL = '/estatistica/sebo/'
ANO = 2025


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


async def _tripulante(session, *, uae='11gt', oper='op'):
    user = UserFactory(unidade=uae)
    session.add(user)
    await session.flush()
    trip = TripFactory(user_id=user.id, func='pil', oper=oper, uae=uae)
    session.add(trip)
    await session.flush()
    return trip


async def _voo(session, trip, *, data, arr, simulador=False, uae='11gt'):
    """Missão de uma etapa (decolagem 10:00) com o tripulante a bordo.

    `tvoo` é computado de dep/arr: 12:30 → 150 min.
    """
    missao = Missao(titulo=None, obs=None, uae=uae, is_simulador=simulador)
    session.add(missao)
    await session.flush()
    etapa = Etapa(
        missao_id=missao.id,
        obs=None,
        data=data,
        origem='SBGL',
        destino='SBGL',
        dep=time(10, 0),
        arr=arr,
        anv='2850',
        pousos=1,
        tow=None,
        pax=None,
        carga=None,
        comb=None,
        lub=None,
        nivel=None,
        sagem=True,
        parte1=True,
    )
    session.add(etapa)
    await session.flush()
    session.add(
        TripEtapa(
            etapa_id=etapa.id, func='pil', func_bordo='1P', trip_id=trip.id
        )
    )
    await session.flush()


async def _get(client, token, **params):
    resp = await client.get(
        URL, params={'func': 'pil', 'ano': ANO, **params}, headers=_auth(token)
    )
    assert resp.status_code == HTTPStatus.OK
    return resp.json()['data']


@pytest.fixture
async def frota(session):
    session.add(Aeronave(matricula='2850', active=True, sit='DI', obs=None))
    await session.flush()


async def test_simulador_nao_soma_horas_nem_conta_como_ultimo_voo(
    client, session, token, frota
):
    """Quem só voou simulador fica com 0h, sem último voo, e abaixo de
    quem voou de verdade — mesmo com mais horas de simulador (480 min
    contra 150 reais + 300 de simulador) e com id menor, então a ordem só
    sai certa se o simulador ficar fora e `h_ano` mandar no desempate. A
    sessão de simulador mais recente não encurta o DSV de quem voou real."""
    so_sim = await _tripulante(session)
    real = await _tripulante(session)
    await _voo(session, real, data=date(ANO, 3, 10), arr=time(12, 30))
    await _voo(
        session, real, data=date(ANO, 5, 20), arr=time(15, 0), simulador=True
    )
    await _voo(
        session, so_sim, data=date(ANO, 4, 1), arr=time(18, 0), simulador=True
    )
    await session.commit()
    # `dsv` é contado pelo relógio do banco (current_date); o container da
    # api roda em UTC, então `date.today()` poderia divergir em 1 dia.
    hoje = await session.scalar(select(func.current_date()))

    data = await _get(client, token)

    por_trip = {i['trip_id']: i['voo'] for i in data}
    assert por_trip[real.id] == {
        'h_ano': 150,
        'dsv': (hoje - date(ANO, 3, 10)).days,
        'data_ult_voo': f'{ANO}-03-10',
    }
    assert por_trip[so_sim.id] == {
        'h_ano': 0,
        'dsv': None,
        'data_ult_voo': None,
    }
    ranking = [i['trip_id'] for i in data]
    assert ranking.index(real.id) < ranking.index(so_sim.id)


async def test_so_tripulantes_da_org_ativa(client, session, token, frota):
    """Rota sem gate (o FatBird a chama com token de tripulante sem role):
    o escopo por `Tripulante.uae` é a única barreira — o roster e os
    cartões de outra unidade não podem aparecer."""
    nosso = await _tripulante(session)
    alheio = await _tripulante(session, uae='1gt')
    await _voo(
        session, alheio, data=date(ANO, 3, 10), arr=time(12, 30), uae='1gt'
    )
    await session.commit()

    ids = {i['trip_id'] for i in await _get(client, token)}

    assert nosso.id in ids
    assert alheio.id not in ids


async def test_func_bordo_filtra_horas_sem_tirar_o_tripulante(
    client, session, token, frota
):
    """`func_bordo` recorta as etapas que somam, não quem aparece: a etapa
    voada como 1P não conta para `IN`, e o tripulante segue listado com
    0h."""
    trip = await _tripulante(session)
    await _voo(session, trip, data=date(ANO, 3, 10), arr=time(12, 30))
    await session.commit()

    # Filtros de lista vão como array JSON (`parse_str_list`).
    em_in = await _get(client, token, func_bordo='["IN"]')
    em_1p = await _get(client, token, func_bordo='["1P"]')

    assert {i['trip_id']: i['voo']['h_ano'] for i in em_in}[trip.id] == 0
    assert {i['trip_id']: i['voo']['h_ano'] for i in em_1p}[trip.id] == 150


async def test_oper_filtra_tripulantes(client, session, token, frota):
    operacional = await _tripulante(session, oper='op')
    instrutor = await _tripulante(session, oper='in')
    await session.commit()

    ids = {i['trip_id'] for i in await _get(client, token, oper='["in"]')}

    assert instrutor.id in ids
    assert operacional.id not in ids
