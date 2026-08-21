"""Isolamento cross-org do endpoint GET /estatistica/horas-anv.

Duas dimensões de escopo, ambas exercitadas aqui:

- **Frota**: a org só enxerga aeronaves dos projetos que opera
  (`Aeronave.projeto ∈ TenantProjeto(uae=org)`). Nos seeds, '11gt' opera
  C8 (kc-390) e '1gt' opera C1 (c-130).
- **Horas**: as horas de uma aeronave são só as das etapas voadas em
  missões DA org (`Missao.uae == active_org`). Uma aeronave da frota da org
  voada numa missão de outra org não soma horas para ela.
"""

from datetime import date, time
from http import HTTPStatus

import pytest

from fcontrol_api.models.estatistica.etapa import Etapa, Missao
from fcontrol_api.models.shared.aeronaves import Aeronave

pytestmark = pytest.mark.anyio

URL = '/estatistica/horas-anv/'
ANO = 2025


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


async def _mk_etapa(session, missao_id, *, anv, tvoo_min):
    """Cria uma etapa; tvoo é coluna computada de (arr - dep)."""
    etapa = Etapa(
        missao_id=missao_id,
        obs=None,
        data=date(ANO, 3, 10),
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


@pytest.fixture
async def cenario(session):
    """Frota e etapas das duas orgs.

    - '2850' (projeto C8) → frota da '11gt'.
    - '2860' (projeto C1) → frota da '1gt'.
    - '2850' é voada por uma missão '11gt' (60 min) E por uma '1gt'
      (120 min) — cenário de vazamento de horas.
    - '2860' é voada por uma missão '1gt' (90 min).
    """
    session.add_all([
        Aeronave(matricula='2850', active=True, sit='DI', obs=None),
        Aeronave(
            matricula='2860', active=True, sit='DI', obs=None, projeto='C1'
        ),
    ])

    mis_11 = Missao(titulo=None, obs=None, uae='11gt')
    mis_1a = Missao(titulo=None, obs=None, uae='1gt')
    mis_1b = Missao(titulo=None, obs=None, uae='1gt')
    session.add_all([mis_11, mis_1a, mis_1b])
    await session.flush()

    await _mk_etapa(session, mis_11.id, anv='2850', tvoo_min=60)
    await _mk_etapa(session, mis_1a.id, anv='2850', tvoo_min=120)
    await _mk_etapa(session, mis_1b.id, anv='2860', tvoo_min=90)
    await session.commit()


async def test_sem_org_ativa_retorna_400(client, token_sistema):
    """Sem org ativa no token_sistema (contexto sem lente) → 400."""
    resp = await client.get(
        URL, params={'ano_ref': ANO}, headers=_auth(token_sistema)
    )
    assert resp.status_code == HTTPStatus.BAD_REQUEST


async def test_org_ve_so_frota_e_horas_da_propria_org(client, cenario, token):
    """'11gt' vê só a '2850' (C8) e só as horas da própria missão (60)."""
    resp = await client.get(URL, params={'ano_ref': ANO}, headers=_auth(token))
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()['data']

    matriculas = {item['matricula'] for item in data['items']}
    assert matriculas == {'2850'}  # '2860' (C1) é da frota da '1gt'

    row = next(i for i in data['items'] if i['matricula'] == '2850')
    # 60 (missão '11gt') e NÃO 180 — a etapa de 120 min é de missão '1gt'.
    assert row['total_tvoo'] == 60
    assert data['total_tvoo'] == 60


async def test_outra_org_nao_ve_frota_nem_horas_alheias(
    client, cenario, users, make_org_token
):
    """'1gt' vê só a '2860'; '2850' (C8) fica fora mesmo tendo voado p/ ela."""
    _, other = users
    token_1gt = await make_org_token(other, active_org='1gt')

    resp = await client.get(
        URL, params={'ano_ref': ANO}, headers=_auth(token_1gt)
    )
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()['data']

    matriculas = {item['matricula'] for item in data['items']}
    assert matriculas == {'2860'}

    row = next(i for i in data['items'] if i['matricula'] == '2860')
    assert row['total_tvoo'] == 90
    assert data['total_tvoo'] == 90
