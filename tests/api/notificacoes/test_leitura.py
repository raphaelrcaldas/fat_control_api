"""Lista, contador e ciclo de leitura das notificações diretas.

O sino é self-service: sem `permission_checker`, o escopo vem de dentro
(o próprio `user_id`). O contador precisa usar o MESMO predicado da
lista — se divergir, o badge acusa item que a lista não mostra.
"""

from datetime import datetime, timezone
from http import HTTPStatus

import pytest
from sqlalchemy import select

from fcontrol_api.models.shared.notificacao import Notificacao
from tests.api.notificacoes.conftest import auth

pytestmark = pytest.mark.anyio


async def test_lista_traz_as_proprias_diretas(
    client, users, token, make_direta
):
    """As diretas do usuário aparecem; a de terceiro, não."""
    user, other_user = users
    minha = await make_direta(user, titulo='Minha')
    dele = await make_direta(other_user, titulo='Dele')

    response = await client.get('/notificacoes/', headers=auth(token))

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    ids = {n['id'] for n in body['data']}
    assert minha.id in ids
    assert dele.id not in ids
    assert body['total'] == 1


async def test_contador_bate_com_a_lista(client, users, token, make_direta):
    """Duas não lidas + uma lida: contador acusa 2, lista mostra 3."""
    user, _ = users
    await make_direta(user, titulo='Nova 1')
    await make_direta(user, titulo='Nova 2')
    await make_direta(
        user, titulo='Antiga', read_at=datetime.now(timezone.utc)
    )

    lista = await client.get('/notificacoes/', headers=auth(token))
    contador = await client.get('/notificacoes/contador', headers=auth(token))

    assert lista.json()['total'] == 3
    data = contador.json()['data']
    assert data['nao_lidas'] == 2
    assert data['tarefas'] == 0
    assert data['total'] == 2


async def test_apenas_pendentes_filtra_as_lidas(
    client, users, token, make_direta
):
    """`apenas_pendentes=true` esconde o que já teve desfecho."""
    user, _ = users
    pendente = await make_direta(user, titulo='Pendente')
    await make_direta(user, titulo='Lida', read_at=datetime.now(timezone.utc))

    response = await client.get(
        '/notificacoes/',
        params={'apenas_pendentes': True},
        headers=auth(token),
    )

    body = response.json()
    assert body['total'] == 1
    assert body['data'][0]['id'] == pendente.id


async def test_marcar_lida_idempotente(
    client, session, users, token, make_direta
):
    """Marcar duas vezes responde 200 e não move o `read_at` original."""
    user, _ = users
    notif = await make_direta(user)

    primeira = await client.patch(
        f'/notificacoes/{notif.id}/lida', headers=auth(token)
    )
    assert primeira.status_code == HTTPStatus.OK
    read_at = primeira.json()['data']['read_at']
    assert read_at is not None

    segunda = await client.patch(
        f'/notificacoes/{notif.id}/lida', headers=auth(token)
    )
    assert segunda.status_code == HTTPStatus.OK
    assert segunda.json()['data']['read_at'] == read_at

    contador = await client.get('/notificacoes/contador', headers=auth(token))
    assert contador.json()['data']['nao_lidas'] == 0


async def test_marcar_lida_de_terceiro_404(
    client, session, users, token, make_direta
):
    """Notificação de outro usuário não existe para quem pede — 404."""
    _, other_user = users
    dele = await make_direta(other_user)

    response = await client.patch(
        f'/notificacoes/{dele.id}/lida', headers=auth(token)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND

    # E continua não lida no banco.
    db_notif = await session.scalar(
        select(Notificacao).where(Notificacao.id == dele.id)
    )
    assert db_notif.read_at is None


async def test_marcar_todas_lidas_idempotente(
    client, users, token, make_direta
):
    """A segunda chamada não tem o que marcar e o contador segue zerado."""
    user, _ = users
    await make_direta(user, titulo='A')
    await make_direta(user, titulo='B')

    primeira = await client.post(
        '/notificacoes/marcar-todas-lidas', headers=auth(token)
    )
    assert primeira.status_code == HTTPStatus.OK
    assert '2' in primeira.json()['message']

    segunda = await client.post(
        '/notificacoes/marcar-todas-lidas', headers=auth(token)
    )
    assert segunda.status_code == HTTPStatus.OK
    assert '0' in segunda.json()['message']

    contador = await client.get('/notificacoes/contador', headers=auth(token))
    assert contador.json()['data']['nao_lidas'] == 0


async def test_marcar_todas_lidas_nao_toca_em_terceiro(
    client, session, users, token, make_direta
):
    """O UPDATE em lote é escopado ao dono — não vaza para outro usuário."""
    user, other_user = users
    await make_direta(user)
    dele = await make_direta(other_user)

    await client.post('/notificacoes/marcar-todas-lidas', headers=auth(token))

    db_notif = await session.scalar(
        select(Notificacao).where(Notificacao.id == dele.id)
    )
    assert db_notif.read_at is None


async def test_admin_de_sistema_ve_as_proprias_diretas(
    client, users, token_sistema, make_direta
):
    """Sem org ativa o sino ainda abre (por isso `ActiveOrgOptional`).

    Com `ActiveOrg` o admin de sistema levaria 400 e perderia as próprias
    notificações só por estar no contexto Sistema.
    """
    user, _ = users
    minha = await make_direta(user)

    response = await client.get('/notificacoes/', headers=auth(token_sistema))

    assert response.status_code == HTTPStatus.OK
    assert {n['id'] for n in response.json()['data']} == {minha.id}


async def test_sem_token_401(client):
    """Rota protegida pelo middleware global."""
    response = await client.get('/notificacoes/')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_apagar_a_propria_direta(client, users, token, make_direta):
    """Apagar remove a linha; a segunda tentativa responde 404."""
    user, _ = users
    minha = await make_direta(user)

    response = await client.delete(
        f'/notificacoes/{minha.id}', headers=auth(token)
    )

    assert response.status_code == HTTPStatus.OK

    lista = await client.get('/notificacoes/', headers=auth(token))
    assert lista.json()['total'] == 0

    de_novo = await client.delete(
        f'/notificacoes/{minha.id}', headers=auth(token)
    )
    assert de_novo.status_code == HTTPStatus.NOT_FOUND


async def test_apagar_de_terceiro_404(
    client, session, users, token, make_direta
):
    """A do outro usuário nem existe para quem tenta apagar."""
    _, other_user = users
    dele = await make_direta(other_user)

    response = await client.delete(
        f'/notificacoes/{dele.id}', headers=auth(token)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    db_notif = await session.scalar(
        select(Notificacao).where(Notificacao.id == dele.id)
    )
    assert db_notif is not None


async def test_apagar_tarefa_404(client, session, token, make_tarefa):
    """Tarefa é compartilhada — não se apaga, se resolve (/resolver)."""
    tarefa = await make_tarefa()

    response = await client.delete(
        f'/notificacoes/{tarefa.id}', headers=auth(token)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    db_notif = await session.scalar(
        select(Notificacao).where(Notificacao.id == tarefa.id)
    )
    assert db_notif is not None
