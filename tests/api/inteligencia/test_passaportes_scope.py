"""Isolamento cross-org de passaportes (/inteligencia/passaportes).

Passaportes penduram num tripulante (escopo `Tripulante.uae`). A org ativa
é obrigatória (o tenant é quem vê; system admin não entra na página). Lista
e writes ficam restritos aos tripulantes da unidade; a limpeza de imagens
órfãs, aos usuários inativos da unidade (`User.unidade`).
"""

from http import HTTPStatus

import pytest

from fcontrol_api.models.inteligencia.passaportes import Passaporte
from fcontrol_api.models.security.resources import UserRole
from tests.factories import TripFactory, UserFactory

pytestmark = pytest.mark.anyio

URL = '/inteligencia/passaportes/'
ORFAOS_URL = '/inteligencia/passaportes/orfaos'


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
async def admin_1gt_token(users, session, make_org_token):
    """Token com org ativa '1gt' e vínculo admin nessa org (bypass)."""
    _, other = users
    session.add(UserRole(user_id=other.id, role_id=1, organizacao_id='1gt'))
    await session.commit()
    return await make_org_token(other, active_org='1gt')


async def _mk_trip(session, *, uae, active=True):
    user = UserFactory(unidade=uae)
    user.active = active
    session.add(user)
    await session.flush()
    trip = TripFactory(user_id=user.id, uae=uae)
    session.add(trip)
    await session.flush()
    return user, trip


async def _mk_passaporte(session, user_id, *, file_path=None):
    pp = Passaporte(
        user_id=user_id,
        passaporte='AB123456',
        data_expedicao_passaporte=None,
        validade_passaporte=None,
        visa=None,
        data_expedicao_visa=None,
        validade_visa=None,
        passaporte_file_path=file_path,
        visa_file_path=None,
    )
    session.add(pp)
    await session.flush()
    return pp


# ── Lista ──────────────────────────────────────────────────────────


async def test_lista_so_traz_tripulantes_da_org(client, session, token):
    """Lista da '11gt' não mostra tripulante da '1gt'."""
    u11, _ = await _mk_trip(session, uae='11gt')
    u1, _ = await _mk_trip(session, uae='1gt')
    await _mk_passaporte(session, u11.id)
    await _mk_passaporte(session, u1.id)
    await session.commit()

    resp = await client.get(URL, headers=_auth(token))
    assert resp.status_code == HTTPStatus.OK
    ids = {row['user_id'] for row in resp.json()['data']}
    assert u11.id in ids
    assert u1.id not in ids


async def test_lista_exige_org_ativa(client, session, users, make_token):
    """Sem org ativa no token → 400 (rota não é mais opcional)."""
    user, _ = users
    # vínculo admin sem org só p/ passar o permission gate; a falta de
    # active_org é o que barra (400).
    session.add(UserRole(user_id=user.id, role_id=1, organizacao_id=None))
    await session.commit()
    token = await make_token(user)

    resp = await client.get(URL, headers=_auth(token))
    assert resp.status_code == HTTPStatus.BAD_REQUEST


# ── Upsert / Delete por trip_id ────────────────────────────────────


async def test_upsert_cross_org_404(client, session, token):
    """Admin da '11gt' não faz upsert em tripulante da '1gt'."""
    _, trip1 = await _mk_trip(session, uae='1gt')
    await session.commit()

    resp = await client.put(
        f'{URL}{trip1.id}',
        json={'passaporte': 'ZZ999999'},
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND


async def test_delete_cross_org_404(client, session, token):
    """Admin da '11gt' não apaga passaporte de tripulante da '1gt'."""
    u1, trip1 = await _mk_trip(session, uae='1gt')
    await _mk_passaporte(session, u1.id)
    await session.commit()

    resp = await client.delete(f'{URL}{trip1.id}', headers=_auth(token))
    assert resp.status_code == HTTPStatus.NOT_FOUND


# ── Registros órfãos ───────────────────────────────────────────────


async def test_orfaos_escopado_por_org(client, session, token):
    """Órfãos só listam registros de inativos da própria org."""
    u11, _ = await _mk_trip(session, uae='11gt', active=False)
    u1, _ = await _mk_trip(session, uae='1gt', active=False)
    await _mk_passaporte(session, u11.id, file_path='passaporte/x/a.jpg')
    await _mk_passaporte(session, u1.id, file_path='passaporte/y/b.jpg')
    await session.commit()

    resp = await client.get(ORFAOS_URL, headers=_auth(token))
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()['data']
    ids = {item['user_id'] for item in data['itens']}
    assert u11.id in ids
    assert u1.id not in ids
    assert data['total_registros'] == 1


async def test_orfaos_delete_remove_registro(client, session, token):
    """DELETE /orfaos apaga o registro inteiro do militar inativo."""
    u11, _ = await _mk_trip(session, uae='11gt', active=False)
    pp = await _mk_passaporte(session, u11.id, file_path='passaporte/x/a.jpg')
    await session.commit()

    resp = await client.request(
        'DELETE',
        ORFAOS_URL,
        json={'user_ids': [u11.id]},
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['registros'] == 1

    session.expire_all()
    assert await session.get(Passaporte, pp.id) is None


async def test_orfaos_delete_nao_remove_de_outra_org(client, session, token):
    """DELETE /orfaos da '11gt' ignora registro órfão da '1gt'."""
    u1, _ = await _mk_trip(session, uae='1gt', active=False)
    pp = await _mk_passaporte(session, u1.id, file_path='passaporte/y/b.jpg')
    await session.commit()

    resp = await client.request(
        'DELETE',
        ORFAOS_URL,
        json={'user_ids': [u1.id]},
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['registros'] == 0

    assert await session.get(Passaporte, pp.id) is not None


# ── Busca por usuário (self-service do FatBird) ────────────────────


async def test_by_user_cross_org_nao_vaza(client, session, admin_1gt_token):
    """Ter a permissão na SUA org não dá acesso ao passaporte de OUTRA.

    A permissão responde "pode ver passaportes?", não "pode ver ESTE
    passaporte". Sem escopo do alvo, um admin da '1gt' leria o número do
    passaporte de um tripulante da '11gt' só trocando o id na URL.
    """
    alheio, _ = await _mk_trip(session, uae='11gt')
    await _mk_passaporte(session, alheio.id)
    await session.commit()

    resp = await client.get(
        f'{URL}user/{alheio.id}', headers=_auth(admin_1gt_token)
    )

    assert resp.json()['data'] is None
