"""
Testes para o endpoint GET /indisp/{id}.

Rota de ITEM (não de lista): o escopo vem da QUERY, via join com
Tripulante.uae == active_org — o id é sequencial e sem esse filtro
qualquer token válido leria a indisponibilidade de qualquer militar do
sistema. Sem gate de permissão de propósito (mesmo racional do
GET /indisp/user/{id}): a lista de tripulação já expõe a
indisponibilidade de todos e o tripulante do FatBird não tem role.

Também não filtra `deleted_at`: o deep-link do sino sobrevive à remoção
e a página precisa da linha excluída para dizer que foi removida.
"""

from datetime import datetime, timezone
from http import HTTPStatus

import pytest

from fcontrol_api.security import create_access_token
from tests.factories import IndispFactory, TripFactory, UserFactory

pytestmark = pytest.mark.anyio


def _fatbird_token_sem_role(user, active_org='11gt'):
    """Token forjado sem role, no formato que o FatBird emite.

    Não usa `make_org_token`/`token_sem_perm` do conftest de cima: eles
    injetam uma role admin quando o usuário não tem nenhuma (bypass), o
    que mascararia a prova de que a rota é aberta mesmo sem role — o
    ponto central do caso "dono lê a própria".
    """
    return create_access_token(
        data={
            'sub': f'tripulante {user.id}',
            'user_id': user.id,
            'app_client': 'fatbird',
            'active_org': active_org,
        }
    )


async def test_dono_le_a_propria_sem_role(client, users, indisp):
    """O tripulante lê a própria indisponibilidade sem ter role nenhuma.

    `other_user` já é tripulante ativo da '11gt' pelo `trip_alvo`
    (autouse do conftest do módulo) e é o dono de `indisp`.
    """
    _, other_user = users
    token = _fatbird_token_sem_role(other_user)

    response = await client.get(
        f'/indisp/{indisp.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['data']['id'] == indisp.id
    assert resp['data']['user_id'] == other_user.id


async def test_indisp_de_outra_org_retorna_404(client, session, users, token):
    """IDOR: indisponibilidade de tripulante de outra org não vaza.

    Usa um TERCEIRO usuário (não `other_user`): o `trip_alvo` do
    conftest já torna `other_user` tripulante da própria '11gt', o que
    mascararia o isolamento cross-org caso ele também ganhasse um
    vínculo na '1gt' aqui.
    """
    user, _ = users

    de_outra_org = UserFactory(unidade='1gt')
    session.add(de_outra_org)
    await session.flush()

    trip = TripFactory(
        user_id=de_outra_org.id, uae='1gt', active=True, func='mc'
    )
    session.add(trip)
    await session.commit()

    indisp_outra_org = IndispFactory(
        user_id=de_outra_org.id,
        created_by=user.id,
    )
    session.add(indisp_outra_org)
    await session.commit()
    await session.refresh(indisp_outra_org)

    response = await client.get(
        f'/indisp/{indisp_outra_org.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    resp = response.json()
    assert resp['status'] == 'error'
    assert 'não encontrada' in resp['message']


async def test_indisp_id_inexistente_retorna_404(client, token):
    """Testa que ID não existente retorna 404."""
    response = await client.get(
        '/indisp/999999',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    resp = response.json()
    assert resp['status'] == 'error'
    assert 'não encontrada' in resp['message']


async def test_indisp_soft_deleted_retorna_200(client, session, indisp, token):
    """Registro apagado continua acessível pelo item — não é 404.

    A página do deep-link depende disso para dizer "esta indisponibilidade
    foi removida" em vez de quebrar com um 404 genérico.
    """
    indisp.deleted_at = datetime.now(timezone.utc)
    session.add(indisp)
    await session.commit()

    response = await client.get(
        f'/indisp/{indisp.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['data']['deleted_at'] is not None


async def test_get_indisp_without_token_fails(client, indisp):
    """Testa que requisição sem token falha."""
    response = await client.get(f'/indisp/{indisp.id}')

    assert response.status_code == HTTPStatus.UNAUTHORIZED
