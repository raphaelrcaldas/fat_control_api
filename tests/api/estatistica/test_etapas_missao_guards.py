"""Testes de router dos guards de etapas/missao da estatistica.

Cobre as validacoes adicionadas nos endpoints:
- colisao de tripulante nos endpoints atomicos (POST/PUT with-etapas),
  tanto interna ao payload quanto contra o banco;
- consistencia tvoo x soma de OIs em PUT /etapas/{id} ao mudar o horario,
  e a rejeicao de etapa que atravessa o dia;
- filtro is_simulador cobrindo o modo flat (nao so o agrupado) e o
  is_simulador exposto no output agrupado.

Convencao: `org_token` traz active_org='11gt' (org canonica dos seeds).
As aeronaves e tripulantes sao semeados por fixture; missoes/etapas de
apoio ("ja existentes no banco") sao criadas direto via session, no mesmo
padrao do test_esfaer_resumo.
"""

from datetime import date, time
from http import HTTPStatus

import pytest
from sqlalchemy import select

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

ETAPAS_URL = '/estatistica/etapas/'
MISSAO_URL = '/estatistica/missao/'
DATA = date(2025, 3, 10)


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


# ── Fixtures de apoio ──────────────────────────────────────────────


@pytest.fixture
async def anvs(session):
    """Duas aeronaves reais (voo) e uma de simulador."""
    session.add_all([
        Aeronave(matricula='2850', active=True, sit='DI', obs=None),
        Aeronave(matricula='2851', active=True, sit='DI', obs=None),
        Aeronave(
            matricula='9990', active=True, sit='DI', obs=None, is_sim=True
        ),
    ])
    await session.commit()


@pytest.fixture
async def trips(session):
    """Dois tripulantes reais (com User) para vincular a etapas."""
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
    """EsforcoAereo + TipoMissao para compor OIs."""
    esf = EsforcoAereo(
        tipo='AVIAO',
        modelo='C-105',
        grupo='COMPREP',
        prog='PRPO',
        sub_prog=None,
        aplicacao=None,
    )
    tipo = TipoMissao(cod='ADT', desc='Adestramento')
    session.add_all([esf, tipo])
    await session.flush()
    await session.commit()
    return esf.id, tipo.id


# ── Helpers de payload / criacao direta ────────────────────────────


def _mins(dep: str, arr: str) -> int:
    d = int(dep[:2]) * 60 + int(dep[3:5])
    a = int(arr[:2]) * 60 + int(arr[3:5])
    if a == 0 and d > 0:
        a = 1440
    return a - d


def _pl_etapa(anv, dep, arr, *, data='2025-03-10', trips=None, ois=None):
    """Monta um dict de EtapaCreateNested/EtapaUpdateNested."""
    return {
        'data': data,
        'origem': 'SBGL',
        'destino': 'SBGL',
        'dep': dep,
        'arr': arr,
        'tvoo': _mins(dep, arr),
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


async def _mk_missao(session, *, is_simulador=False):
    missao = Missao(titulo=None, obs=None, uae='11gt')
    missao.is_simulador = is_simulador
    session.add(missao)
    await session.flush()
    return missao


async def _mk_etapa(
    session, missao_id, *, anv, dep, arr, data=DATA, trip_ids=()
):
    etapa = Etapa(
        missao_id=missao_id,
        obs=None,
        data=data,
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
    await session.flush()
    return etapa


# ── Fix 2: colisao de tripulante nos endpoints atomicos ────────────


async def test_with_etapas_colisao_trip_interna_rejeita(
    client, org_token, anvs, trips
):
    """Duas etapas do payload, mesma data e horarios sobrepostos, com o
    mesmo tripulante (aeronaves distintas p/ isolar do guard de anv)."""
    t1, _ = trips
    body = {
        'titulo': None,
        'obs': None,
        'is_simulador': False,
        'etapas': [
            _pl_etapa('2850', '10:00:00', '11:00:00', trips=[t1]),
            _pl_etapa('2851', '10:30:00', '11:30:00', trips=[t1]),
        ],
    }
    resp = await client.post(
        f'{MISSAO_URL}with-etapas', json=body, headers=_auth(org_token)
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert 'conflito de hor' in resp.json()['message'].lower()


async def test_with_etapas_colisao_trip_externa_rejeita(
    client, session, org_token, anvs, trips
):
    """Etapa nova colide com etapa ja persistida (outra missao) que usa o
    mesmo tripulante em horario sobreposto."""
    t1, _ = trips
    missao_db = await _mk_missao(session)
    await _mk_etapa(
        session,
        missao_db.id,
        anv='2850',
        dep=time(10, 0),
        arr=time(11, 0),
        trip_ids=[t1],
    )
    await session.commit()

    body = {
        'titulo': None,
        'obs': None,
        'is_simulador': False,
        'etapas': [_pl_etapa('2851', '10:30:00', '11:30:00', trips=[t1])],
    }
    resp = await client.post(
        f'{MISSAO_URL}with-etapas', json=body, headers=_auth(org_token)
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert 'ja escalado' in resp.json()['message'].lower()


async def test_with_etapas_trip_sem_sobreposicao_ok(
    client, org_token, anvs, trips
):
    """Mesmo tripulante em etapas que apenas se tocam (11:00) nao colide."""
    t1, _ = trips
    body = {
        'titulo': 'Missao OK',
        'obs': None,
        'is_simulador': False,
        'etapas': [
            _pl_etapa('2850', '10:00:00', '11:00:00', trips=[t1]),
            _pl_etapa('2851', '11:00:00', '12:00:00', trips=[t1]),
        ],
    }
    resp = await client.post(
        f'{MISSAO_URL}with-etapas', json=body, headers=_auth(org_token)
    )
    assert resp.status_code == HTTPStatus.CREATED


async def test_update_with_etapas_colisao_trip_externa_rejeita(
    client, session, org_token, anvs, trips
):
    """PUT que adiciona etapa colidindo com etapa de OUTRA missao (mesmo
    trip, horario sobreposto) e barrado."""
    t1, _ = trips
    missao_a = await _mk_missao(session)
    await _mk_etapa(
        session,
        missao_a.id,
        anv='2850',
        dep=time(10, 0),
        arr=time(11, 0),
        trip_ids=[t1],
    )
    missao_b = await _mk_missao(session)
    await session.commit()

    body = {
        'titulo': None,
        'obs': None,
        'delete_ids': [],
        'update': [],
        'create': [_pl_etapa('2851', '10:30:00', '11:30:00', trips=[t1])],
    }
    resp = await client.put(
        f'{MISSAO_URL}{missao_b.id}/with-etapas',
        json=body,
        headers=_auth(org_token),
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert 'ja escalado' in resp.json()['message'].lower()


async def test_update_with_etapas_nao_colide_consigo_mesma(
    client, session, org_token, anvs, trips
):
    """Atualizar a propria etapa (mesmo trip/slot) nao dispara colisao — a
    etapa sob edicao entra em exclude_ids."""
    t1, _ = trips
    missao = await _mk_missao(session)
    etapa = await _mk_etapa(
        session,
        missao.id,
        anv='2850',
        dep=time(10, 0),
        arr=time(11, 0),
        trip_ids=[t1],
    )
    await session.commit()

    body = {
        'titulo': None,
        'obs': None,
        'delete_ids': [],
        'update': [
            {
                'id': etapa.id,
                **_pl_etapa('2850', '10:00:00', '11:00:00', trips=[t1]),
            }
        ],
        'create': [],
    }
    resp = await client.put(
        f'{MISSAO_URL}{missao.id}/with-etapas',
        json=body,
        headers=_auth(org_token),
    )
    assert resp.status_code == HTTPStatus.OK


# ── Fix 4: tvoo x OIs em PUT /etapas/{id} ──────────────────────────


async def test_put_etapa_ois_divergem_ao_mudar_horario_rejeita(
    client, session, org_token, anvs, oi_refs
):
    """Mudar dep/arr (novo tvoo) sem reenviar as OIs: a soma antiga deixa
    de bater com o tvoo novo e o update e barrado."""
    esf_id, tipo_id = oi_refs
    missao = await _mk_missao(session)
    etapa = await _mk_etapa(
        session, missao.id, anv='2850', dep=time(10, 0), arr=time(11, 0)
    )
    session.add(
        OIEtapa(
            etapa_id=etapa.id,
            esf_aer_id=esf_id,
            tipo_missao_id=tipo_id,
            reg='d',
            tvoo=60,
        )
    )
    await session.commit()

    resp = await client.put(
        f'{ETAPAS_URL}{etapa.id}',
        json={'arr': '11:30:00'},  # novo tvoo=90, OIs somam 60
        headers=_auth(org_token),
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert 'soma das ois' in resp.json()['message'].lower()


async def test_put_etapa_atravessa_dia_rejeita(
    client, session, org_token, anvs
):
    """arr <= dep (sem ser 00:00) atravessa o dia e e barrado."""
    missao = await _mk_missao(session)
    etapa = await _mk_etapa(
        session, missao.id, anv='2850', dep=time(10, 0), arr=time(11, 0)
    )
    await session.commit()

    resp = await client.put(
        f'{ETAPAS_URL}{etapa.id}',
        json={'dep': '10:00:00', 'arr': '09:00:00'},
        headers=_auth(org_token),
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert 'atravessar o dia' in resp.json()['message'].lower()


async def test_put_etapa_muda_horario_e_ois_coerentes_ok(
    client, session, org_token, anvs, oi_refs
):
    """Mudar o horario reenviando OIs que somam o novo tvoo e aceito."""
    esf_id, tipo_id = oi_refs
    missao = await _mk_missao(session)
    etapa = await _mk_etapa(
        session, missao.id, anv='2850', dep=time(10, 0), arr=time(11, 0)
    )
    session.add(
        OIEtapa(
            etapa_id=etapa.id,
            esf_aer_id=esf_id,
            tipo_missao_id=tipo_id,
            reg='d',
            tvoo=60,
        )
    )
    await session.commit()

    resp = await client.put(
        f'{ETAPAS_URL}{etapa.id}',
        json={
            'arr': '11:30:00',
            'oi_etapas': [
                {
                    'esf_aer_id': esf_id,
                    'tipo_missao_id': tipo_id,
                    'reg': 'd',
                    'tvoo': 90,
                }
            ],
        },
        headers=_auth(org_token),
    )
    assert resp.status_code == HTTPStatus.OK


# ── Fix 1 / Fix 3: is_simulador no flat e no grouped ───────────────


async def test_lista_flat_exclui_simulador_por_padrao(
    client, session, org_token, anvs
):
    """O modo flat deve honrar is_simulador (default False): so etapas de
    missao normal aparecem; com is_simulador=true, so as de simulador."""
    normal = await _mk_missao(session, is_simulador=False)
    sim = await _mk_missao(session, is_simulador=True)
    await _mk_etapa(
        session, normal.id, anv='2850', dep=time(10, 0), arr=time(11, 0)
    )
    await _mk_etapa(
        session, sim.id, anv='9990', dep=time(10, 0), arr=time(11, 0)
    )
    await session.commit()

    resp = await client.get(
        ETAPAS_URL,
        params={'flat': 'true', 'data_ini': '2025-03-01'},
        headers=_auth(org_token),
    )
    assert resp.status_code == HTTPStatus.OK
    body = resp.json()
    missao_ids = {e['missao_id'] for e in body['data']}
    assert normal.id in missao_ids
    assert sim.id not in missao_ids

    resp_sim = await client.get(
        ETAPAS_URL,
        params={
            'flat': 'true',
            'is_simulador': 'true',
            'data_ini': '2025-03-01',
        },
        headers=_auth(org_token),
    )
    body_sim = resp_sim.json()
    missao_ids_sim = {e['missao_id'] for e in body_sim['data']}
    assert missao_ids_sim == {sim.id}


async def test_lista_grouped_expoe_is_simulador(
    client, session, org_token, anvs
):
    """O output agrupado carrega o is_simulador real da missao."""
    normal = await _mk_missao(session, is_simulador=False)
    await _mk_etapa(
        session, normal.id, anv='2850', dep=time(10, 0), arr=time(11, 0)
    )
    await session.commit()

    resp = await client.get(
        ETAPAS_URL,
        params={'data_ini': '2025-03-01'},
        headers=_auth(org_token),
    )
    assert resp.status_code == HTTPStatus.OK
    missoes = {m['id']: m for m in resp.json()['data']}
    assert missoes[normal.id]['is_simulador'] is False


async def test_with_etapas_anv_simulador_incoerente_rejeita(
    client, org_token, anvs, trips
):
    """Missao normal com aeronave de simulador e barrada (guard de
    consistencia anv x tipo de missao, pre-existente mas exercitado aqui
    junto do fluxo atomico)."""
    body = {
        'titulo': None,
        'obs': None,
        'is_simulador': False,
        'etapas': [_pl_etapa('9990', '10:00:00', '11:00:00')],
    }
    resp = await client.post(
        f'{MISSAO_URL}with-etapas', json=body, headers=_auth(org_token)
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert 'simulador' in resp.json()['message'].lower()


async def test_seed_etapa_persistida_visivel_no_flat(
    client, session, org_token, anvs
):
    """Sanidade: etapa criada e visivel no flat (garante o caminho feliz
    da paginacao plana)."""
    missao = await _mk_missao(session)
    etapa = await _mk_etapa(
        session, missao.id, anv='2850', dep=time(10, 0), arr=time(11, 0)
    )
    await session.commit()

    resp = await client.get(
        ETAPAS_URL,
        params={'flat': 'true', 'data_ini': '2025-03-01'},
        headers=_auth(org_token),
    )
    assert resp.status_code == HTTPStatus.OK
    ids = {e['id'] for e in resp.json()['data']}
    assert etapa.id in ids

    # E o registro realmente existe no banco (sanidade da sessao de teste)
    exists = await session.scalar(select(Etapa.id).where(Etapa.id == etapa.id))
    assert exists == etapa.id
