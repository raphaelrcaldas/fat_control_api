"""Testes de router dos guards de etapas/missao da estatistica.

Cobre as validacoes adicionadas nos endpoints:
- colisao de tripulante nos endpoints atomicos (POST/PUT with-etapas),
  tanto interna ao payload quanto contra o banco;
- consistencia tvoo x soma de OIs em PUT /etapas/{id} ao mudar o horario,
  e a rejeicao de etapa que atravessa o dia;
- filtro is_simulador na listagem e o is_simulador exposto no output.

Convencao: `token` traz active_org='11gt' (org canonica dos seeds).
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
    client, token, anvs, trips
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
        f'{MISSAO_URL}with-etapas', json=body, headers=_auth(token)
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert 'conflito de hor' in resp.json()['message'].lower()


async def test_with_etapas_colisao_trip_externa_rejeita(
    client, session, token, anvs, trips
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
        f'{MISSAO_URL}with-etapas', json=body, headers=_auth(token)
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert 'ja escalado' in resp.json()['message'].lower()


async def test_with_etapas_trip_sem_sobreposicao_ok(
    client, token, anvs, trips
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
        f'{MISSAO_URL}with-etapas', json=body, headers=_auth(token)
    )
    assert resp.status_code == HTTPStatus.CREATED


async def test_update_with_etapas_colisao_trip_externa_rejeita(
    client, session, token, anvs, trips
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
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert 'ja escalado' in resp.json()['message'].lower()


async def test_update_with_etapas_nao_colide_consigo_mesma(
    client, session, token, anvs, trips
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
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.OK


# ── Fix 4: tvoo x OIs em PUT /etapas/{id} ──────────────────────────


async def test_put_etapa_ois_divergem_ao_mudar_horario_rejeita(
    client, session, token, anvs, oi_refs
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
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert 'soma das ois' in resp.json()['message'].lower()


async def test_put_etapa_atravessa_dia_rejeita(client, session, token, anvs):
    """arr <= dep (sem ser 00:00) atravessa o dia e e barrado."""
    missao = await _mk_missao(session)
    etapa = await _mk_etapa(
        session, missao.id, anv='2850', dep=time(10, 0), arr=time(11, 0)
    )
    await session.commit()

    resp = await client.put(
        f'{ETAPAS_URL}{etapa.id}',
        json={'dep': '10:00:00', 'arr': '09:00:00'},
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert 'atravessar o dia' in resp.json()['message'].lower()


async def test_put_etapa_muda_horario_e_ois_coerentes_ok(
    client, session, token, anvs, oi_refs
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
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.OK


# ── Fix 1 / Fix 3: is_simulador na listagem ────────────────────────


async def test_lista_exclui_simulador_por_padrao(client, session, token, anvs):
    """A listagem deve honrar is_simulador (default False): so missao
    normal aparece; com is_simulador=true, so as de simulador."""
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
        params={'data_ini': '2025-03-01'},
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.OK
    missao_ids = {m['id'] for m in resp.json()['data']}
    assert normal.id in missao_ids
    assert sim.id not in missao_ids

    resp_sim = await client.get(
        ETAPAS_URL,
        params={'is_simulador': 'true', 'data_ini': '2025-03-01'},
        headers=_auth(token),
    )
    missao_ids_sim = {m['id'] for m in resp_sim.json()['data']}
    assert missao_ids_sim == {sim.id}


async def test_lista_grouped_expoe_is_simulador(client, session, token, anvs):
    """O output agrupado carrega o is_simulador real da missao."""
    normal = await _mk_missao(session, is_simulador=False)
    await _mk_etapa(
        session, normal.id, anv='2850', dep=time(10, 0), arr=time(11, 0)
    )
    await session.commit()

    resp = await client.get(
        ETAPAS_URL,
        params={'data_ini': '2025-03-01'},
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.OK
    missoes = {m['id']: m for m in resp.json()['data']}
    assert missoes[normal.id]['is_simulador'] is False


async def test_with_etapas_anv_simulador_incoerente_rejeita(
    client, token, anvs, trips
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
        f'{MISSAO_URL}with-etapas', json=body, headers=_auth(token)
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert 'simulador' in resp.json()['message'].lower()


async def test_seed_etapa_persistida_visivel_na_listagem(
    client, session, token, anvs
):
    """Sanidade: etapa criada e visivel na listagem (caminho feliz)."""
    missao = await _mk_missao(session)
    etapa = await _mk_etapa(
        session, missao.id, anv='2850', dep=time(10, 0), arr=time(11, 0)
    )
    await session.commit()

    resp = await client.get(
        ETAPAS_URL,
        params={'data_ini': '2025-03-01'},
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.OK
    ids = {e['id'] for m in resp.json()['data'] for e in m['etapas']}
    assert etapa.id in ids

    # E o registro realmente existe no banco (sanidade da sessao de teste)
    exists = await session.scalar(select(Etapa.id).where(Etapa.id == etapa.id))
    assert exists == etapa.id


# ── Escopo cross-org do trip_id (o gate autoriza a acao, nao o alvo) ──


@pytest.fixture
async def trip_de_outra_org(session):
    """Tripulante da '1gt' — fora da org ativa do `token` ('11gt')."""
    user = UserFactory()
    session.add(user)
    await session.flush()
    trip = TripFactory(user_id=user.id, uae='1gt')
    session.add(trip)
    await session.flush()
    await session.commit()
    return trip.id


async def test_post_etapa_recusa_trip_de_outra_org(
    client, token, session, anvs, trip_de_outra_org
):
    """POST /etapas/ nao aceita tripulante de outra unidade.

    Sem o escopo, a hora de voo era lancada no nome de militar alheio e
    o GET seguinte devolvia trigrama, nome de guerra e posto dele.
    """
    missao = await _mk_missao(session)
    await session.commit()

    payload = _pl_etapa('2850', '08:00', '09:00', trips=[trip_de_outra_org])
    payload['missao_id'] = missao.id

    resp = await client.post(ETAPAS_URL, json=payload, headers=_auth(token))

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    # Mensagem neutra de proposito: nao revela que o id existe noutra org.
    assert 'encontrado' in resp.json()['message'].lower()

    # Nada foi gravado.
    vinculos = await session.scalars(
        select(TripEtapa).where(TripEtapa.trip_id == trip_de_outra_org)
    )
    assert vinculos.all() == []


async def test_post_with_etapas_recusa_trip_de_outra_org(
    client, token, session, anvs, trip_de_outra_org
):
    """POST /missao/with-etapas idem — e sem criar a missao (rollback)."""
    payload = {
        'titulo': 'Simulador',
        'obs': None,
        'is_simulador': False,
        'etapas': [
            _pl_etapa('2850', '08:00', '09:00', trips=[trip_de_outra_org])
        ],
    }

    resp = await client.post(
        f'{MISSAO_URL}with-etapas', json=payload, headers=_auth(token)
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    missoes = await session.scalars(
        select(Missao).where(Missao.titulo == 'Simulador')
    )
    assert missoes.all() == []


async def test_put_etapa_recusa_trip_de_outra_org(
    client, token, session, anvs, trips, trip_de_outra_org
):
    """PUT /etapas/{id} nao deixa trocar a tripulacao por id alheio."""
    missao = await _mk_missao(session)
    etapa = await _mk_etapa(
        session,
        missao.id,
        anv='2850',
        dep=time(8, 0),
        arr=time(9, 0),
        trip_ids=trips[:1],
    )
    await session.commit()

    resp = await client.put(
        f'{ETAPAS_URL}{etapa.id}',
        json={
            'tripulantes': [
                {
                    'trip_id': trip_de_outra_org,
                    'func': 'mc',
                    'func_bordo': 'MC',
                }
            ]
        },
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    vinculos = await session.scalars(
        select(TripEtapa).where(TripEtapa.trip_id == trip_de_outra_org)
    )
    assert vinculos.all() == []


async def test_post_etapa_aceita_trip_da_propria_org(
    client, token, session, anvs, trips, oi_refs
):
    """Contraprova: o caminho feliz continua passando."""
    missao = await _mk_missao(session)
    await session.commit()

    payload = _pl_etapa('2850', '08:00', '09:00', trips=trips[:1])
    payload['missao_id'] = missao.id

    resp = await client.post(ETAPAS_URL, json=payload, headers=_auth(token))

    assert resp.status_code == HTTPStatus.CREATED


# ── A mensagem de colisao nao pode nomear dado de outra org ────────


@pytest.fixture
async def etapa_de_outra_org(session, anvs):
    """Etapa da '1gt' ocupando 2850 das 08:00 as 09:00 em DATA.

    A deteccao de colisao NAO filtra por org de proposito (uma cauda
    fisica nao voa em duas unidades ao mesmo tempo); o que nao pode
    vazar e a identificacao da etapa alheia.
    """
    user = UserFactory()
    session.add(user)
    await session.flush()
    trip = TripFactory(user_id=user.id, uae='1gt')
    session.add(trip)
    await session.flush()

    missao = Missao(titulo='OPERACAO ALHEIA', obs=None, uae='1gt')
    missao.is_simulador = False
    session.add(missao)
    await session.flush()

    etapa = await _mk_etapa(
        session,
        missao.id,
        anv='2850',
        dep=time(8, 0),
        arr=time(9, 0),
        trip_ids=[trip.id],
    )
    await session.commit()
    return etapa.id, trip.id


async def test_colisao_anv_com_outra_org_nao_vaza_etapa(
    client, token, session, anvs, etapa_de_outra_org
):
    """Colide, mas a frase so cita a sigla da org — nunca id/horario."""
    etapa_alheia_id, _ = etapa_de_outra_org
    missao = await _mk_missao(session)
    await session.commit()

    payload = _pl_etapa('2850', '08:30', '09:30')
    payload['missao_id'] = missao.id

    resp = await client.post(ETAPAS_URL, json=payload, headers=_auth(token))

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    msg = resp.json()['message']
    # A deteccao continua valendo.
    assert '1GT' in msg
    # Mas nada identifica a etapa alheia.
    assert f'#{etapa_alheia_id}' not in msg
    assert '08:00' not in msg


async def test_colisao_trip_com_outra_org_nao_vaza_etapa(
    client, token, session, anvs, trips, etapa_de_outra_org
):
    """Tripulante alheio ja escalado: idem, so a sigla da org."""
    etapa_alheia_id, trip_alheio = etapa_de_outra_org

    # O militar alheio nao pode nem ser anexado (escopo de trip_id),
    # entao a colisao se prova pelo lado da aeronave da outra unidade:
    # aqui usamos a 2851, livre, e um trip da propria org — o conflito
    # que resta e o da etapa alheia ocupando a 2850.
    missao = await _mk_missao(session)
    await session.commit()

    payload = _pl_etapa('2850', '08:30', '09:30', trips=trips[:1])
    payload['missao_id'] = missao.id

    resp = await client.post(ETAPAS_URL, json=payload, headers=_auth(token))

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    msg = resp.json()['message']
    assert f'#{etapa_alheia_id}' not in msg


async def test_colisao_na_propria_org_mantem_detalhe(
    client, token, session, anvs, trips
):
    """Contraprova: dentro da org, a mensagem segue util e detalhada."""
    missao = await _mk_missao(session)
    etapa = await _mk_etapa(
        session,
        missao.id,
        anv='2850',
        dep=time(8, 0),
        arr=time(9, 0),
        trip_ids=trips[:1],
    )
    await session.commit()

    payload = _pl_etapa('2850', '08:30', '09:30')
    payload['missao_id'] = missao.id

    resp = await client.post(ETAPAS_URL, json=payload, headers=_auth(token))

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    msg = resp.json()['message']
    assert f'#{etapa.id}' in msg
    assert '08:00' in msg


# ── Apagar a ultima etapa nao pode deixar missao orfa ──────────────


async def test_delete_ultima_etapa_apaga_a_missao(
    client, token, session, anvs, trips
):
    """Missao sem etapa e invisivel na listagem (join) — vai junto."""
    missao = await _mk_missao(session)
    etapa = await _mk_etapa(
        session,
        missao.id,
        anv='2850',
        dep=time(8, 0),
        arr=time(9, 0),
        trip_ids=trips[:1],
    )
    missao_id = missao.id
    await session.commit()

    resp = await client.delete(f'{ETAPAS_URL}{etapa.id}', headers=_auth(token))

    assert resp.status_code == HTTPStatus.OK
    session.expire_all()
    assert await session.get(Missao, missao_id) is None


async def test_delete_etapa_preserva_missao_com_outras(
    client, token, session, anvs, trips
):
    """Contraprova: sobrando etapa, a missao permanece."""
    missao = await _mk_missao(session)
    etapa_a = await _mk_etapa(
        session,
        missao.id,
        anv='2850',
        dep=time(8, 0),
        arr=time(9, 0),
        trip_ids=trips[:1],
    )
    await _mk_etapa(
        session,
        missao.id,
        anv='2850',
        dep=time(10, 0),
        arr=time(11, 0),
        trip_ids=trips[:1],
    )
    missao_id = missao.id
    await session.commit()

    resp = await client.delete(
        f'{ETAPAS_URL}{etapa_a.id}', headers=_auth(token)
    )

    assert resp.status_code == HTTPStatus.OK
    session.expire_all()
    assert await session.get(Missao, missao_id) is not None


# ── Ano fora da janela plausivel e recusado pela API ───────────────


async def test_post_etapa_recusa_ano_absurdo(
    client, token, session, anvs, trips
):
    """Ano 0006 (digitacao) nao pode entrar pelo backend.

    O `min`/`max` do <input type="date"> fecha so a porta do navegador;
    a API precisa recusar de qualquer cliente. Etapa com ano fora da
    janela some dos paineis (que consultam `ano >= 2020`) mas continua
    na listagem por janela de data — dado fantasma.
    """
    missao = await _mk_missao(session)
    await session.commit()

    payload = _pl_etapa(
        '2850', '08:00', '09:00', data='0006-03-10', trips=trips[:1]
    )
    payload['missao_id'] = missao.id

    resp = await client.post(ETAPAS_URL, json=payload, headers=_auth(token))

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_post_with_etapas_recusa_ano_absurdo(
    client, token, session, anvs, trips
):
    """O endpoint atomico tambem recusa — e nada e gravado."""
    payload = {
        'titulo': 'ANO RUIM',
        'obs': None,
        'is_simulador': False,
        'etapas': [
            _pl_etapa(
                '2850',
                '08:00',
                '09:00',
                data='9999-01-01',
                trips=trips[:1],
            )
        ],
    }

    resp = await client.post(
        f'{MISSAO_URL}with-etapas', json=payload, headers=_auth(token)
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    missoes = await session.scalars(
        select(Missao).where(Missao.titulo == 'ANO RUIM')
    )
    assert missoes.all() == []


async def test_put_etapa_recusa_ano_absurdo(
    client, token, session, anvs, trips
):
    """EtapaUpdate nao herda de EtapaBase — precisa do proprio guard."""
    missao = await _mk_missao(session)
    etapa = await _mk_etapa(
        session,
        missao.id,
        anv='2850',
        dep=time(8, 0),
        arr=time(9, 0),
        trip_ids=trips[:1],
    )
    await session.commit()

    resp = await client.put(
        f'{ETAPAS_URL}{etapa.id}',
        json={'data': '0006-03-10'},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
