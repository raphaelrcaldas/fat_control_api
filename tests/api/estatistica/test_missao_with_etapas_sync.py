"""Testes de escrita do PUT /estatistica/missao/{id}/with-etapas.

O endpoint sincroniza a missao e suas etapas em tres blocos: delete em
lote (payload.delete_ids), update em lote (payload.update) e create
(payload.create). Os guards de colisao ja sao cobertos por
`test_etapas_missao_guards.py`; aqui o alvo e o efeito no banco:

- delete_ids remove a etapa e as linhas filhas (OIs e tripulantes),
  sem tocar nas demais etapas da missao;
- delete_ids de outra missao e recusado, sem apagar nada;
- create persiste a etapa com tripulantes e OIs, normalizando
  origem/destino/anv para maiusculo;
- update substitui OIs e tripulantes em vez de acumular.

Convencao: `token` traz active_org='11gt' (org canonica dos seeds).
Fixtures autocontidas de proposito — este arquivo nao depende do
arquivo de guards.
"""

from datetime import date, time
from http import HTTPStatus

import pytest
from sqlalchemy import func, select

from fcontrol_api.models.estatistica.esf_aer import EsforcoAereo
from fcontrol_api.models.estatistica.etapa import (
    Etapa,
    Missao,
    OIEtapa,
    TipoMissao,
    TripEtapa,
)
from fcontrol_api.models.shared.aeronaves import Aeronave
from tests.factories import TripFactory, UserFactory

pytestmark = pytest.mark.anyio

MISSAO_URL = '/estatistica/missao/'
DATA = date(2025, 3, 10)


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
async def anvs(session):
    session.add_all([
        Aeronave(matricula='2860', active=True, sit='DI', obs=None),
        Aeronave(matricula='2861', active=True, sit='DI', obs=None),
    ])
    await session.commit()


@pytest.fixture
async def trips(session):
    ids: list[int] = []
    for _ in range(2):
        user = UserFactory()
        session.add(user)
        await session.flush()
        trip = TripFactory(user_id=user.id)
        session.add(trip)
        await session.flush()
        ids.append(trip.id)
    await session.commit()
    return ids


@pytest.fixture
async def oi_refs(session):
    esf = EsforcoAereo(
        tipo='AVIAO',
        modelo='C-105',
        grupo='COMPREP',
        prog='PRPO',
        sub_prog=None,
        aplicacao=None,
    )
    tipo = TipoMissao(cod='ADS', desc='Adestramento sync')
    session.add_all([esf, tipo])
    await session.flush()
    await session.commit()
    return esf.id, tipo.id


def _pl_etapa(anv, dep, arr, *, trips=None, ois=None, origem='SBGL'):
    """Monta um dict de EtapaCreateNested/EtapaUpdateNested."""
    d = int(dep[:2]) * 60 + int(dep[3:5])
    a = int(arr[:2]) * 60 + int(arr[3:5])
    return {
        'data': '2025-03-10',
        'origem': origem,
        'destino': 'SBGL',
        'dep': dep,
        'arr': arr,
        'tvoo': a - d,
        'anv': anv,
        'pousos': 1,
        'tow': None,
        'pax': None,
        'carga': None,
        'comb': None,
        'lub': None,
        'nivel': None,
        'sagem': True,
        'parte1': True,
        'obs': None,
        'tripulantes': [
            {'trip_id': t, 'func': 'mc', 'func_bordo': 'MC'}
            for t in (trips or [])
        ],
        'oi_etapas': ois or [],
        'pqd': [],
        'revo': [],
        'heavy_cds': [],
    }


def _oi(esf_id, tipo_id, tvoo, reg='d'):
    return {
        'esf_aer_id': esf_id,
        'tipo_missao_id': tipo_id,
        'reg': reg,
        'tvoo': tvoo,
    }


async def _mk_missao(session):
    missao = Missao(titulo=None, obs=None, uae='11gt')
    missao.is_simulador = False
    session.add(missao)
    await session.flush()
    return missao


async def _mk_etapa(session, missao_id, *, anv, dep, arr, trip_ids=(), ois=()):
    etapa = Etapa(
        missao_id=missao_id,
        obs=None,
        data=DATA,
        origem='SBGL',
        destino='SBGL',
        dep=dep,
        arr=arr,
        anv=anv,
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
    for tid in trip_ids:
        session.add(
            TripEtapa(
                etapa_id=etapa.id, func='mc', func_bordo='MC', trip_id=tid
            )
        )
    for esf_id, tipo_id, tvoo in ois:
        session.add(
            OIEtapa(
                etapa_id=etapa.id,
                esf_aer_id=esf_id,
                tipo_missao_id=tipo_id,
                reg='d',
                tvoo=tvoo,
            )
        )
    await session.flush()
    return etapa


async def _contar(session, model, etapa_id):
    return await session.scalar(
        select(func.count())
        .select_from(model)
        .where(model.etapa_id == etapa_id)
    )


# ── Bloco delete em lote ───────────────────────────────────────────


async def test_delete_ids_remove_etapa_e_seus_filhos(
    client, session, token, anvs, trips, oi_refs
):
    """delete_ids apaga a etapa e as linhas filhas, e so essa etapa."""
    esf_id, tipo_id = oi_refs
    t1, t2 = trips
    missao = await _mk_missao(session)
    alvo = await _mk_etapa(
        session,
        missao.id,
        anv='2860',
        dep=time(10, 0),
        arr=time(11, 0),
        trip_ids=[t1],
        ois=[(esf_id, tipo_id, 60)],
    )
    sobrevivente = await _mk_etapa(
        session,
        missao.id,
        anv='2861',
        dep=time(14, 0),
        arr=time(15, 0),
        trip_ids=[t2],
        ois=[(esf_id, tipo_id, 60)],
    )
    await session.commit()
    alvo_id, sobrevivente_id = alvo.id, sobrevivente.id

    resp = await client.put(
        f'{MISSAO_URL}{missao.id}/with-etapas',
        json={
            'titulo': None,
            'obs': None,
            'delete_ids': [alvo_id],
            'update': [],
            'create': [],
        },
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    session.expire_all()
    assert await session.get(Etapa, alvo_id) is None
    assert await _contar(session, OIEtapa, alvo_id) == 0
    assert await _contar(session, TripEtapa, alvo_id) == 0
    # a outra etapa da missao fica intacta, com os filhos dela
    assert await session.get(Etapa, sobrevivente_id) is not None
    assert await _contar(session, OIEtapa, sobrevivente_id) == 1
    assert await _contar(session, TripEtapa, sobrevivente_id) == 1


async def test_delete_id_de_outra_missao_e_recusado(
    client, session, token, anvs, trips
):
    """Etapa de outra missao em delete_ids nao apaga nada (ownership)."""
    t1, _ = trips
    missao_a = await _mk_missao(session)
    alheia = await _mk_etapa(
        session,
        missao_a.id,
        anv='2860',
        dep=time(10, 0),
        arr=time(11, 0),
        trip_ids=[t1],
    )
    missao_b = await _mk_missao(session)
    await session.commit()
    alheia_id = alheia.id

    resp = await client.put(
        f'{MISSAO_URL}{missao_b.id}/with-etapas',
        json={
            'titulo': None,
            'obs': None,
            'delete_ids': [alheia_id],
            'update': [],
            'create': [],
        },
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    session.expire_all()
    assert await session.get(Etapa, alheia_id) is not None


# ── Bloco create ───────────────────────────────────────────────────


async def test_create_persiste_etapa_com_trips_e_ois(
    client, session, token, anvs, trips, oi_refs
):
    """create grava a etapa nova e suas linhas filhas."""
    esf_id, tipo_id = oi_refs
    t1, _ = trips
    missao = await _mk_missao(session)
    await session.commit()
    missao_id = missao.id

    resp = await client.put(
        f'{MISSAO_URL}{missao_id}/with-etapas',
        json={
            'titulo': 'Missao com etapa nova',
            'obs': None,
            'delete_ids': [],
            'update': [],
            'create': [
                _pl_etapa(
                    '2860',
                    '10:00:00',
                    '11:00:00',
                    trips=[t1],
                    ois=[_oi(esf_id, tipo_id, 60)],
                )
            ],
        },
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    session.expire_all()
    nova = await session.scalar(
        select(Etapa).where(Etapa.missao_id == missao_id)
    )
    assert nova is not None
    assert nova.anv == '2860'
    assert nova.pousos == 1
    assert nova.sagem is True
    assert await _contar(session, TripEtapa, nova.id) == 1
    assert await _contar(session, OIEtapa, nova.id) == 1

    oi = await session.scalar(
        select(OIEtapa).where(OIEtapa.etapa_id == nova.id)
    )
    assert oi.esf_aer_id == esf_id
    assert oi.tipo_missao_id == tipo_id
    assert oi.reg == 'd'
    assert oi.tvoo == 60

    trip_etapa = await session.scalar(
        select(TripEtapa).where(TripEtapa.etapa_id == nova.id)
    )
    assert trip_etapa.trip_id == t1
    assert trip_etapa.func == 'mc'
    assert trip_etapa.func_bordo == 'MC'


async def test_create_normaliza_icao_para_maiusculo(
    client, session, token, anvs, trips
):
    """origem/destino chegam minusculos e sao gravados em maiusculo."""
    missao = await _mk_missao(session)
    await session.commit()
    missao_id = missao.id

    resp = await client.put(
        f'{MISSAO_URL}{missao_id}/with-etapas',
        json={
            'titulo': None,
            'obs': None,
            'delete_ids': [],
            'update': [],
            'create': [
                _pl_etapa('2860', '10:00:00', '11:00:00', origem='sbgl')
            ],
        },
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    session.expire_all()
    nova = await session.scalar(
        select(Etapa).where(Etapa.missao_id == missao_id)
    )
    assert nova.origem == 'SBGL'
    assert nova.destino == 'SBGL'


# ── Bloco update ───────────────────────────────────────────────────


async def test_update_substitui_ois_em_vez_de_acumular(
    client, session, token, anvs, trips, oi_refs
):
    """update apaga OIs/tripulantes antigos antes de reinserir."""
    esf_id, tipo_id = oi_refs
    t1, t2 = trips
    missao = await _mk_missao(session)
    etapa = await _mk_etapa(
        session,
        missao.id,
        anv='2860',
        dep=time(10, 0),
        arr=time(11, 0),
        trip_ids=[t1],
        ois=[(esf_id, tipo_id, 30), (esf_id, tipo_id, 30)],
    )
    await session.commit()
    etapa_id = etapa.id
    assert await _contar(session, OIEtapa, etapa_id) == 2

    resp = await client.put(
        f'{MISSAO_URL}{missao.id}/with-etapas',
        json={
            'titulo': None,
            'obs': None,
            'delete_ids': [],
            'update': [
                {
                    'id': etapa_id,
                    **_pl_etapa(
                        '2860',
                        '10:00:00',
                        '11:00:00',
                        trips=[t2],
                        ois=[_oi(esf_id, tipo_id, 60)],
                    ),
                }
            ],
            'create': [],
        },
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    session.expire_all()
    # dois OIs viraram um; o tripulante trocou, nao somou
    assert await _contar(session, OIEtapa, etapa_id) == 1
    assert await _contar(session, TripEtapa, etapa_id) == 1
    trip_etapa = await session.scalar(
        select(TripEtapa).where(TripEtapa.etapa_id == etapa_id)
    )
    assert trip_etapa.trip_id == t2
