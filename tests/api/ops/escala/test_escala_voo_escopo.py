"""Escopo dos dados de voo em GET /ops/escala/disponiveis.

Os dois números de voo da tela — `tvoo_year` (minutos no ano de `date_end`,
que ordena o `sort=horas_voo`) e `data_ult_voo` — enxergam só o que a tela
enxerga: missões da org ativa e, com filtro de projeto, só etapas voadas em
aeronave daquele projeto.

Os dois também contam só as etapas em que o tripulante exerceu a **própria
função**: piloto que voou como O3 (função `oe` a bordo) não carrega essas
horas para a prioridade de piloto — senão desceria na fila por horas que não
são de `pil` — nem renova por ali a data do último voo.

A janela de tempo é o que os separa: só as horas são anuais. O último voo é
o mais recente que existir, de qualquer ano.
"""

from datetime import date, time
from http import HTTPStatus

import pytest

from fcontrol_api.models.estatistica.etapa import Etapa, Missao, TripEtapa
from fcontrol_api.models.shared.aeronaves import Aeronave
from tests.factories import TripFactory, UserFactory

pytestmark = pytest.mark.anyio

URL = '/ops/escala/disponiveis'
ANO = 2025
# Frota dos seeds: 'C8' é o kc-390 (projeto da '11gt'), 'C1' é o c-130.
ANV = '2850'
ANV_OUTRO_PROJ = '2860'

# QuadsType.id=1 -> group 'sobr' (elegível para escala).
TIPO_ELEGIVEL = 1


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def _params(**over):
    base = {
        'date_start': f'{ANO}-06-01',
        'date_end': f'{ANO}-06-30',
        'tipo_quad_id': TIPO_ELEGIVEL,
        'funcs': ['pil'],
        'sort': 'horas_voo',
    }
    base.update(over)
    return base


async def _mk_trip(session, user_id, *, func='pil'):
    trip = TripFactory(
        user_id=user_id,
        uae='11gt',
        active=True,
        func=func,
        oper='op',
        proj='kc-390',
        data_op=date(2020, 1, 1),
    )
    session.add(trip)
    await session.flush()
    return trip


async def _mk_frota(session):
    """Uma aeronave de cada projeto: '2850' (C8/kc-390) e '2860' (C1/c-130)."""
    session.add_all([
        Aeronave(matricula=ANV, active=True, sit='DI', obs=None),
        Aeronave(
            matricula=ANV_OUTRO_PROJ,
            active=True,
            sit='DI',
            obs=None,
            projeto='C1',
        ),
    ])
    await session.flush()


async def _mk_missao(session, *, uae='11gt'):
    missao = Missao(titulo=None, obs=None, uae=uae)
    session.add(missao)
    await session.flush()
    return missao


async def _mk_etapa(session, missao_id, *, tvoo_min, anv=ANV, data=None):
    """Cria uma etapa no ano de referência; `tvoo` é computada de arr - dep."""
    etapa = Etapa(
        missao_id=missao_id,
        obs=None,
        data=data or date(ANO, 3, 10),
        origem='SBGL',
        destino='SBGL',
        dep=time(10, 0),
        arr=time(10 + tvoo_min // 60, tvoo_min % 60),
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
    return etapa


async def _voo(
    session, missao_id, trip, *, tvoo_min, func, func_bordo, anv=ANV, data=None
):
    """Lança uma etapa para o tripulante numa função a bordo específica."""
    etapa = await _mk_etapa(
        session, missao_id, tvoo_min=tvoo_min, anv=anv, data=data
    )
    session.add(
        TripEtapa(
            etapa_id=etapa.id,
            func=func,
            func_bordo=func_bordo,
            trip_id=trip.id,
        )
    )
    await session.flush()
    return etapa


@pytest.fixture
async def cenario(session, users):
    """Dois pilotos e um operador da '11gt', com horas em funções distintas.

    - `pil_o3`: 60 min como piloto (2P) **e** 300 min como O3 (função `oe`).
    - `pil_puro`: 120 min como piloto (1P).
    - `oe`: 180 min como O3 — a função dele *é* `oe`, então as horas contam.
    """
    user, other = users
    user_oe = UserFactory()
    session.add(user_oe)
    await session.flush()

    await _mk_frota(session)
    missao = await _mk_missao(session)

    pil_o3 = await _mk_trip(session, user.id)
    pil_puro = await _mk_trip(session, other.id)
    oe = await _mk_trip(session, user_oe.id, func='oe')

    await _voo(
        session, missao.id, pil_o3, tvoo_min=60, func='pil', func_bordo='2P'
    )
    await _voo(
        session, missao.id, pil_o3, tvoo_min=300, func='oe', func_bordo='O3'
    )
    await _voo(
        session, missao.id, pil_puro, tvoo_min=120, func='pil', func_bordo='1P'
    )
    await _voo(
        session, missao.id, oe, tvoo_min=180, func='oe', func_bordo='O3'
    )

    await session.commit()
    return {'pil_o3': pil_o3, 'pil_puro': pil_puro, 'oe': oe}


def _trips_por_func(payload):
    return {s['func']: s['trips'] for s in payload['sections']}


async def test_horas_como_o3_nao_entram_no_tvoo_do_piloto(
    client, cenario, token_sem_perm
):
    """O piloto que também voou como O3 conta só os 60 min de `pil`."""
    resp = await client.get(
        URL, params=_params(), headers=_auth(token_sem_perm)
    )

    assert resp.status_code == HTTPStatus.OK
    trips = _trips_por_func(resp.json()['data'])['pil']
    por_id = {t['id']: t for t in trips}

    # 60, e não 360 — os 300 min de O3 são de outra função.
    assert por_id[cenario['pil_o3'].id]['tvoo_year'] == 60
    assert por_id[cenario['pil_puro'].id]['tvoo_year'] == 120


async def test_sort_horas_voo_nao_penaliza_piloto_que_voou_como_o3(
    client, cenario, token_sem_perm
):
    """Prioridade por horas: 60 min de `pil` vem antes de 120 min de `pil`.

    Somando as horas de O3 o `pil_o3` iria para 360 min e cairia para o fim
    da fila — exatamente o vazamento que esta ordenação não pode ter.
    """
    resp = await client.get(
        URL, params=_params(), headers=_auth(token_sem_perm)
    )

    trips = _trips_por_func(resp.json()['data'])['pil']
    assert [t['id'] for t in trips] == [
        cenario['pil_o3'].id,
        cenario['pil_puro'].id,
    ]


async def test_operador_mantem_as_horas_da_propria_funcao(
    client, cenario, token_sem_perm
):
    """O filtro não pode zerar quem voa na função dele: `oe` fica com 180."""
    resp = await client.get(
        URL, params=_params(funcs=['pil', 'oe']), headers=_auth(token_sem_perm)
    )

    secoes = _trips_por_func(resp.json()['data'])
    por_id = {t['id']: t for t in secoes['oe']}
    assert por_id[cenario['oe'].id]['tvoo_year'] == 180


async def test_piloto_sem_voo_na_propria_funcao_fica_zerado(
    client, session, users, token_sem_perm
):
    """Piloto que no ano só voou como O3 entra com 0 e lidera a prioridade."""
    user, other = users
    await _mk_frota(session)
    missao = await _mk_missao(session)

    so_o3 = await _mk_trip(session, user.id)
    pil_puro = await _mk_trip(session, other.id)
    await _voo(
        session, missao.id, so_o3, tvoo_min=300, func='oe', func_bordo='O3'
    )
    await _voo(
        session, missao.id, pil_puro, tvoo_min=60, func='pil', func_bordo='1P'
    )
    await session.commit()

    resp = await client.get(
        URL, params=_params(), headers=_auth(token_sem_perm)
    )

    trips = _trips_por_func(resp.json()['data'])['pil']
    assert [(t['id'], t['tvoo_year']) for t in trips] == [
        (so_o3.id, 0),
        (pil_puro.id, 60),
    ]


async def test_horas_de_missao_de_outra_org_nao_contam(
    client, session, users, token_sem_perm
):
    """A soma é da org ativa: voo em missão da '1gt' não entra na '11gt'."""
    user, _ = users
    await _mk_frota(session)
    mis_11 = await _mk_missao(session)
    mis_1gt = await _mk_missao(session, uae='1gt')

    trip = await _mk_trip(session, user.id)
    await _voo(
        session, mis_11.id, trip, tvoo_min=60, func='pil', func_bordo='1P'
    )
    await _voo(
        session, mis_1gt.id, trip, tvoo_min=300, func='pil', func_bordo='1P'
    )
    await session.commit()

    resp = await client.get(
        URL, params=_params(), headers=_auth(token_sem_perm)
    )

    assert resp.status_code == HTTPStatus.OK
    trips = _trips_por_func(resp.json()['data'])['pil']
    # 60, e não 360 — os 300 min foram voados numa missão da '1gt'.
    assert [(t['id'], t['tvoo_year']) for t in trips] == [(trip.id, 60)]


@pytest.fixture
async def cenario_projetos(session, users):
    """Piloto com voo em dois projetos na mesma org: 60 em C8, 300 em C1."""
    user, _ = users
    await _mk_frota(session)
    missao = await _mk_missao(session)

    trip = await _mk_trip(session, user.id)
    await _voo(
        session, missao.id, trip, tvoo_min=60, func='pil', func_bordo='1P'
    )
    await _voo(
        session,
        missao.id,
        trip,
        tvoo_min=300,
        func='pil',
        func_bordo='1P',
        anv=ANV_OUTRO_PROJ,
    )
    await session.commit()
    return trip


async def test_filtro_de_projeto_restringe_as_horas(
    client, cenario_projetos, token_sem_perm
):
    """Escalando o kc-390, as horas de c-130 (C1) ficam de fora."""
    resp = await client.get(
        URL, params=_params(proj='kc-390'), headers=_auth(token_sem_perm)
    )

    assert resp.status_code == HTTPStatus.OK
    trips = _trips_por_func(resp.json()['data'])['pil']
    assert [(t['id'], t['tvoo_year']) for t in trips] == [
        (cenario_projetos.id, 60)
    ]


async def test_sem_filtro_de_projeto_soma_todos_os_projetos(
    client, cenario_projetos, token_sem_perm
):
    """Sem `proj`, a escala é de toda a org — as horas também."""
    resp = await client.get(
        URL, params=_params(), headers=_auth(token_sem_perm)
    )

    trips = _trips_por_func(resp.json()['data'])['pil']
    assert [(t['id'], t['tvoo_year']) for t in trips] == [
        (cenario_projetos.id, 360)
    ]


async def test_data_ult_voo_ignora_missao_de_outra_org(
    client, session, users, token_sem_perm
):
    """O voo mais recente foi numa missão da '1gt' — não vale para a '11gt'."""
    user, _ = users
    await _mk_frota(session)
    mis_11 = await _mk_missao(session)
    mis_1gt = await _mk_missao(session, uae='1gt')

    trip = await _mk_trip(session, user.id)
    await _voo(
        session,
        mis_11.id,
        trip,
        tvoo_min=60,
        func='pil',
        func_bordo='1P',
        data=date(ANO, 3, 10),
    )
    await _voo(
        session,
        mis_1gt.id,
        trip,
        tvoo_min=60,
        func='pil',
        func_bordo='1P',
        data=date(ANO, 5, 20),
    )
    await session.commit()

    resp = await client.get(
        URL, params=_params(), headers=_auth(token_sem_perm)
    )

    assert resp.status_code == HTTPStatus.OK
    trips = _trips_por_func(resp.json()['data'])['pil']
    assert trips[0]['data_ult_voo'] == f'{ANO}-03-10'


async def test_data_ult_voo_ignora_voo_em_outra_funcao(
    client, session, users, token_sem_perm
):
    """O voo mais recente foi como O3 — não renova a data do piloto."""
    user, _ = users
    await _mk_frota(session)
    missao = await _mk_missao(session)

    trip = await _mk_trip(session, user.id)
    await _voo(
        session,
        missao.id,
        trip,
        tvoo_min=60,
        func='pil',
        func_bordo='1P',
        data=date(ANO, 3, 10),
    )
    await _voo(
        session,
        missao.id,
        trip,
        tvoo_min=60,
        func='oe',
        func_bordo='O3',
        data=date(ANO, 5, 20),
    )
    await session.commit()

    resp = await client.get(
        URL, params=_params(), headers=_auth(token_sem_perm)
    )

    trips = _trips_por_func(resp.json()['data'])['pil']
    assert trips[0]['data_ult_voo'] == f'{ANO}-03-10'


@pytest.fixture
async def cenario_data_projetos(session, users):
    """Piloto com voo em C8 (março) e, mais recente, em C1 (maio)."""
    user, _ = users
    await _mk_frota(session)
    missao = await _mk_missao(session)

    trip = await _mk_trip(session, user.id)
    await _voo(
        session,
        missao.id,
        trip,
        tvoo_min=60,
        func='pil',
        func_bordo='1P',
        data=date(ANO, 3, 10),
    )
    await _voo(
        session,
        missao.id,
        trip,
        tvoo_min=60,
        func='pil',
        func_bordo='1P',
        anv=ANV_OUTRO_PROJ,
        data=date(ANO, 5, 20),
    )
    await session.commit()
    return trip


async def test_data_ult_voo_respeita_filtro_de_projeto(
    client, cenario_data_projetos, token_sem_perm
):
    """Escalando o kc-390, o voo de maio (c-130) não conta como último."""
    resp = await client.get(
        URL, params=_params(proj='kc-390'), headers=_auth(token_sem_perm)
    )

    trips = _trips_por_func(resp.json()['data'])['pil']
    assert trips[0]['data_ult_voo'] == f'{ANO}-03-10'


async def test_data_ult_voo_sem_filtro_de_projeto_pega_o_mais_recente(
    client, cenario_data_projetos, token_sem_perm
):
    """Sem `proj`, o último voo é o mais recente da org, em qualquer frota."""
    resp = await client.get(
        URL, params=_params(), headers=_auth(token_sem_perm)
    )

    trips = _trips_por_func(resp.json()['data'])['pil']
    assert trips[0]['data_ult_voo'] == f'{ANO}-05-20'


async def test_ult_voo_de_ano_anterior_vale_mas_nao_soma_horas(
    client, session, users, token_sem_perm
):
    """Só as horas são anuais: o último voo é o mais recente de qualquer ano.

    Piloto que voou pela última vez em 2024 aparece com essa data — e com
    0 min no ano de `date_end`.
    """
    user, _ = users
    await _mk_frota(session)
    missao = await _mk_missao(session)

    trip = await _mk_trip(session, user.id)
    await _voo(
        session,
        missao.id,
        trip,
        tvoo_min=120,
        func='pil',
        func_bordo='1P',
        data=date(ANO - 1, 11, 5),
    )
    await session.commit()

    resp = await client.get(
        URL, params=_params(), headers=_auth(token_sem_perm)
    )

    assert resp.status_code == HTTPStatus.OK
    trip_resp = _trips_por_func(resp.json()['data'])['pil'][0]
    assert trip_resp['data_ult_voo'] == f'{ANO - 1}-11-05'
    assert trip_resp['tvoo_year'] == 0
