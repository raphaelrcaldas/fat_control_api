"""Isolamento cross-org de cartões de saúde (/aeromedica/cartoes-saude).

Cartões penduram num User (diretório global) escopado por `User.unidade`.
A org ativa é a lente: a lista, o create/update/delete e a limpeza de
órfãos só operam sobre usuários da própria unidade e ativos.

Nos seeds há duas orgs: '11gt' (canônica) e '1gt' (cross-org).
"""

import json
from http import HTTPStatus

import pytest
from sqlalchemy import select

from fcontrol_api.models.aeromedica.atas import AtaInspecao
from fcontrol_api.models.aeromedica.cartoes import CartaoSaude
from fcontrol_api.models.security.logs import UserActionLog
from fcontrol_api.models.security.resources import UserRole
from tests.factories import TripFactory, UserFactory

pytestmark = pytest.mark.anyio

URL = '/aeromedica/cartoes-saude/'
ORFAOS_URL = '/aeromedica/cartoes-saude/orfaos'
LOG_RESOURCE = 'aeromedica.cartoes'


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
async def admin_1gt_token(users, session, make_org_token):
    """Token com org ativa '1gt' e vínculo admin nessa org (bypass)."""
    _, other = users
    session.add(UserRole(user_id=other.id, role_id=1, organizacao_id='1gt'))
    await session.commit()
    return await make_org_token(other, active_org='1gt')


async def _mk_user(session, *, unidade, active=True):
    user = UserFactory(unidade=unidade)
    user.active = active
    session.add(user)
    await session.flush()
    return user


async def _mk_cartao(session, user_id):
    cartao = CartaoSaude(
        user_id=user_id, cemal=None, tovn=None, imae=None, prontuario=None
    )
    session.add(cartao)
    await session.flush()
    return cartao


# ── Lista ──────────────────────────────────────────────────────────


async def test_lista_so_traz_usuarios_da_org_ativa(client, session, token):
    """A lista da '11gt' não mostra usuário lotado na '1gt'."""
    u11 = await _mk_user(session, unidade='11gt')
    u1 = await _mk_user(session, unidade='1gt')
    await _mk_cartao(session, u11.id)
    await _mk_cartao(session, u1.id)
    await session.commit()

    resp = await client.get(URL, headers=_auth(token))
    assert resp.status_code == HTTPStatus.OK
    ids = {row['user']['id'] for row in resp.json()['data']}
    assert u11.id in ids
    assert u1.id not in ids


async def test_vinculo_tripulante_de_outra_org_nao_conta(
    client, session, token
):
    """Vínculo de tripulante em outra org não marca `tripulante=True`.

    Usuário lotado na '11gt' (aparece na lista) mas com vínculo de
    tripulante ativo só na '1gt': a flag deve refletir apenas o vínculo
    da org ativa.
    """
    u11 = await _mk_user(session, unidade='11gt')
    trip = TripFactory(user_id=u11.id, uae='1gt')
    session.add(trip)
    await session.commit()

    resp = await client.get(URL, headers=_auth(token))
    assert resp.status_code == HTTPStatus.OK
    row = next(r for r in resp.json()['data'] if r['user']['id'] == u11.id)
    assert row['tripulante'] is False

    # E o filtro tripulante=true não o traz.
    resp = await client.get(
        URL, params={'tripulante': True}, headers=_auth(token)
    )
    ids = {r['user']['id'] for r in resp.json()['data']}
    assert u11.id not in ids


# ── Create ─────────────────────────────────────────────────────────


async def test_create_cross_org_404(client, session, token):
    """Admin da '11gt' não cria cartão p/ usuário da '1gt'."""
    u1 = await _mk_user(session, unidade='1gt')
    await session.commit()

    resp = await client.post(
        URL,
        json={
            'user_id': u1.id,
            'prontuario': None,
            'cemal': None,
            'tovn': None,
            'imae': None,
        },
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND


async def test_create_para_inativo_404(client, session, token):
    """Não cria cartão p/ usuário inativo (mesmo da própria org)."""
    u11 = await _mk_user(session, unidade='11gt', active=False)
    await session.commit()

    resp = await client.post(
        URL,
        json={
            'user_id': u11.id,
            'prontuario': None,
            'cemal': None,
            'tovn': None,
            'imae': None,
        },
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND


# ── Update / Delete ────────────────────────────────────────────────


async def test_update_cross_org_404(client, session, token):
    """Admin da '11gt' não edita cartão de usuário da '1gt'."""
    u1 = await _mk_user(session, unidade='1gt')
    cartao = await _mk_cartao(session, u1.id)
    await session.commit()

    resp = await client.put(
        f'{URL}{cartao.id}',
        json={'prontuario': '999'},
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND


async def test_delete_cross_org_404(client, session, token):
    """Admin da '11gt' não apaga cartão de usuário da '1gt'."""
    u1 = await _mk_user(session, unidade='1gt')
    cartao = await _mk_cartao(session, u1.id)
    await session.commit()

    resp = await client.delete(f'{URL}{cartao.id}', headers=_auth(token))
    assert resp.status_code == HTTPStatus.NOT_FOUND


# ── Órfãos ─────────────────────────────────────────────────────────


async def _mk_ata(session, user_id):
    ata = AtaInspecao(
        user_id=user_id,
        file_path=f'atas-inspecao/{user_id}/a.pdf',
        file_name='a.pdf',
        file_size=1024,
    )
    session.add(ata)
    await session.flush()
    return ata


async def test_orfaos_escopado_por_org(
    client, session, token, admin_1gt_token
):
    """Órfãos agrega cartão + atas de inativos, só da própria org."""
    u11 = await _mk_user(session, unidade='11gt', active=False)
    u1 = await _mk_user(session, unidade='1gt', active=False)
    await _mk_cartao(session, u11.id)
    await _mk_ata(session, u11.id)
    await _mk_ata(session, u11.id)
    await _mk_cartao(session, u1.id)
    await session.commit()

    resp = await client.get(ORFAOS_URL, headers=_auth(token))
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()['data']
    ids = {item['user_id'] for item in data['itens']}
    assert u11.id in ids
    assert u1.id not in ids

    row = next(i for i in data['itens'] if i['user_id'] == u11.id)
    assert row['tem_cartao'] is True
    assert row['total_atas'] == 2
    assert data['total_cartoes'] == 1
    assert data['total_atas'] == 2


async def test_orfaos_delete_remove_cartao_e_atas(client, session, token):
    """DELETE /orfaos da própria org apaga cartão E atas do militar."""
    u11 = await _mk_user(session, unidade='11gt', active=False)
    cartao = await _mk_cartao(session, u11.id)
    ata = await _mk_ata(session, u11.id)
    await session.commit()

    resp = await client.request(
        'DELETE',
        ORFAOS_URL,
        json={'user_ids': [u11.id]},
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data'] == {'cartoes': 1, 'atas': 1}

    session.expire_all()
    assert await session.get(CartaoSaude, cartao.id) is None
    assert await session.get(AtaInspecao, ata.id) is None


async def test_orfaos_delete_apaga_trilha_de_auditoria(client, session, token):
    """A limpeza leva a trilha de auditoria junto com os documentos.

    O `before`/`after` guarda as datas de inspeção: mantê-lo deixaria o
    dado de saúde no banco justamente depois de o documento ter sido
    apagado, que é o oposto do propósito da limpeza.
    """
    u11 = await _mk_user(session, unidade='11gt')
    await session.commit()

    # Cartão criado pela API (é o POST que grava o evento); só depois o
    # militar é inativado, senão o create é recusado.
    resp = await client.post(
        URL,
        json={'user_id': u11.id, 'cemal': '2027-01-01'},
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.CREATED

    u11.active = False
    session.add(u11)
    await session.commit()

    resp = await client.request(
        'DELETE',
        ORFAOS_URL,
        json={'user_ids': [u11.id]},
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.OK

    logs = await session.scalars(
        select(UserActionLog).where(
            UserActionLog.resource == LOG_RESOURCE,
            UserActionLog.resource_id == u11.id,
        )
    )
    assert logs.all() == []


async def test_orfaos_delete_nao_remove_de_outra_org(client, session, token):
    """DELETE /orfaos da '11gt' ignora documentos órfãos da '1gt'."""
    u1 = await _mk_user(session, unidade='1gt', active=False)
    cartao = await _mk_cartao(session, u1.id)
    ata = await _mk_ata(session, u1.id)
    await session.commit()

    resp = await client.request(
        'DELETE',
        ORFAOS_URL,
        json={'user_ids': [u1.id]},
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data'] == {'cartoes': 0, 'atas': 0}

    # Cartão e ata da '1gt' continuam no banco.
    assert await session.get(CartaoSaude, cartao.id) is not None
    assert await session.get(AtaInspecao, ata.id) is not None


# ── Self-service FatBird (GET /user/{id}) ──────────────────────────


@pytest.fixture
async def user_token_11gt(users, session, make_org_token):
    """Token '11gt' de usuário com role não-admin (sem permissões)."""
    _, other = users
    session.add(UserRole(user_id=other.id, role_id=2, organizacao_id='11gt'))
    await session.commit()
    return other, await make_org_token(other, active_org='11gt')


async def test_by_user_owner_self_service(client, session, user_token_11gt):
    """O próprio militar vê seu cartão sem 'cartoes-saude.view' (FatBird)."""
    other, tok = user_token_11gt
    cartao = await _mk_cartao(session, other.id)
    await session.commit()

    resp = await client.get(f'{URL}user/{other.id}', headers=_auth(tok))
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['id'] == cartao.id


async def test_by_user_terceiro_sem_view_403(client, session, user_token_11gt):
    """Terceiro sem 'cartoes-saude.view' não lê o cartão de outro militar."""
    _, tok = user_token_11gt
    outro = await _mk_user(session, unidade='11gt')
    await session.commit()

    resp = await client.get(f'{URL}user/{outro.id}', headers=_auth(tok))
    assert resp.status_code == HTTPStatus.FORBIDDEN


async def test_by_user_cross_org_nao_vaza(client, session, admin_1gt_token):
    """Ter a permissão na SUA org não dá acesso ao cartão de OUTRA.

    A permissão responde "pode ver cartões?", não "pode ver ESTE cartão".
    Sem escopo do alvo, um admin da '1gt' leria o prontuário de um militar
    da '11gt' só trocando o id na URL.
    """
    alheio = await _mk_user(session, unidade='11gt')
    await _mk_cartao(session, alheio.id)
    await session.commit()

    resp = await client.get(
        f'{URL}user/{alheio.id}', headers=_auth(admin_1gt_token)
    )

    assert resp.json()['data'] is None


# ── Trilha de auditoria (GET /user/{id}/historico) ─────────────────


async def test_historico_registra_create_e_update(client, session, token):
    """A trilha traz o que a API gravou, do mais recente para o mais antigo.

    O `update` guarda só o delta — é o que o histórico exibe como
    "de → para".
    """
    u11 = await _mk_user(session, unidade='11gt')
    await session.commit()

    resp = await client.post(
        URL,
        json={'user_id': u11.id, 'cemal': '2027-01-01'},
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.CREATED
    cartao_id = resp.json()['data']['id']

    resp = await client.put(
        f'{URL}{cartao_id}',
        json={'cemal': '2028-01-01'},
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.OK

    resp = await client.get(
        f'{URL}user/{u11.id}/historico', headers=_auth(token)
    )
    assert resp.status_code == HTTPStatus.OK
    eventos = resp.json()['data']

    assert [e['action'] for e in eventos] == ['update', 'create']
    # resource_id é o militar, não o cartão: o id do cartão não sobrevive a
    # um delete+recadastro e partiria a linha do tempo em duas.
    assert {e['resource_id'] for e in eventos} == {u11.id}
    assert json.loads(eventos[0]['before']) == {'cemal': '2027-01-01'}
    assert json.loads(eventos[0]['after']) == {'cemal': '2028-01-01'}


async def test_historico_put_sem_mudanca_nao_vira_evento(
    client, session, token
):
    """PUT com o payload já persistido não gera linha na trilha.

    O formulário manda os quatro campos a cada "Atualizar"; sem a guarda de
    diff vazio, todo salvamento viraria um evento sem alteração nenhuma.
    """
    u11 = await _mk_user(session, unidade='11gt')
    await session.commit()

    resp = await client.post(
        URL,
        json={'user_id': u11.id, 'cemal': '2027-01-01'},
        headers=_auth(token),
    )
    cartao_id = resp.json()['data']['id']

    resp = await client.put(
        f'{URL}{cartao_id}',
        json={'cemal': '2027-01-01'},
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.OK

    resp = await client.get(
        f'{URL}user/{u11.id}/historico', headers=_auth(token)
    )
    assert [e['action'] for e in resp.json()['data']] == ['create']


async def test_historico_cross_org_404(client, session, admin_1gt_token):
    """Admin da '1gt' não lê a trilha de um militar da '11gt'.

    O gate autoriza a AÇÃO, não o ALVO: sem o escopo por `User.unidade`, o
    `before`/`after` — que carrega data de inspeção de saúde — sairia só
    trocando o id na URL.
    """
    alheio = await _mk_user(session, unidade='11gt')
    await _mk_cartao(session, alheio.id)
    await session.commit()

    resp = await client.get(
        f'{URL}user/{alheio.id}/historico', headers=_auth(admin_1gt_token)
    )

    assert resp.status_code == HTTPStatus.NOT_FOUND


async def test_historico_sem_view_403(client, session, user_token_11gt):
    """Sem 'aeromedica.cartoes.view' a trilha não abre — nem a própria.

    Diferente do GET do cartão, que abre exceção para o dono (self-service
    do FatBird): a trilha traz quem mexeu e quando, não é dado do militar.
    """
    other, tok = user_token_11gt
    await _mk_cartao(session, other.id)
    await session.commit()

    resp = await client.get(
        f'{URL}user/{other.id}/historico', headers=_auth(tok)
    )

    assert resp.status_code == HTTPStatus.FORBIDDEN
