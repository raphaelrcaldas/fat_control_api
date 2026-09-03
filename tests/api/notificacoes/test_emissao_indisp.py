"""Emissão de notificação pelos endpoints de indisponibilidade.

`create_indisp`/`update_indisp`/`delete_indisp` chamam `notificar_usuarios`
no MESMO commit da mutação (contrato de `services/notificacoes.py`: add
sem commit — quem comita é o call site). O ponto mais frágil é o
`payload['mtv']`: cada endpoint recebe o motivo de uma origem diferente
(schema no create, `model_dump` possivelmente-Enum no update, coluna já
string no delete) e só o create/delete escapam ilesos por acidente se o
`getattr(obj, 'value', obj)` do update não for revisitado.

Reusa as fixtures do conftest do módulo (`users`, `trips`, `token`,
`fatbird_token`) em vez das de `tests/api/indisp/`: aquele conftest
sombreia `token` e faz `other_user` tripulante só da '11gt', mas quem
prova "quem lança a própria não se notifica" precisa do MESMO usuário
como ator e alvo, o que a fixture `trips` daqui já cobre para os dois
usuários de uma vez.
"""

from datetime import date, timedelta
from http import HTTPStatus

import pytest
from sqlalchemy import func, select

from fcontrol_api.enums.notificacao import (
    NotifAudiencia,
    NotifEscopo,
    NotifTipo,
)
from fcontrol_api.models.shared.notificacao import Notificacao
from tests.api.notificacoes.conftest import auth, fatbird_token
from tests.factories import IndispFactory

pytestmark = pytest.mark.anyio

# Data futura o bastante para nunca cair dentro do prazo mínimo de 2 dias
# que o próprio tripulante (sem a permissão 'ops.indisp') tem de
# respeitar — senão os testes de self-service quebram sozinhos com o
# calendário.
FUTURO = date.today() + timedelta(days=10)


def _payload(user_id, inicio=FUTURO, mtv='sde'):
    return {
        'user_id': user_id,
        'date_start': inicio.isoformat(),
        'date_end': (inicio + timedelta(days=3)).isoformat(),
        'mtv': mtv,
        'obs': 'teste de emissão',
    }


async def _notifs_indisp(session, **filtros):
    """Notificações emitidas por `ops.indisp`, filtradas pelo call site."""
    condicoes = [Notificacao.recurso == 'ops.indisp']
    for coluna, valor in filtros.items():
        condicoes.append(getattr(Notificacao, coluna) == valor)

    result = await session.scalars(select(Notificacao).where(*condicoes))
    return result.all()


async def _count_notifs(session):
    return await session.scalar(
        select(func.count())
        .select_from(Notificacao)
        .where(Notificacao.recurso == 'ops.indisp')
    )


@pytest.fixture
async def existing_indisp(session, users, trips):
    """Indisponibilidade já salva, alvo do PUT/DELETE dos testes abaixo.

    Criada direto pelo factory (sem passar pelo POST): o que se quer
    exercitar é a emissão do PUT/DELETE, não a do POST de novo.
    """
    user, other_user = users

    indisp = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=FUTURO,
        date_end=FUTURO + timedelta(days=3),
        mtv='fer',
        obs='original',
    )
    session.add(indisp)
    await session.commit()
    await session.refresh(indisp)
    return indisp


# ── Caso 1: criação gera notificação direta com os campos certos ────


async def test_create_gera_notif_direta(client, session, users, token, trips):
    _, other_user = users

    response = await client.post(
        '/indisp/', json=_payload(other_user.id), headers=auth(token)
    )
    assert response.status_code == HTTPStatus.CREATED

    notifs = await _notifs_indisp(session)
    assert len(notifs) == 1

    notif = notifs[0]
    assert notif.escopo == NotifEscopo.DIRETA.value
    assert notif.audiencia == NotifAudiencia.TRIPULANTE.value
    assert notif.tipo == NotifTipo.INDISP_CRIADA.value
    assert notif.user_id == other_user.id
    assert notif.recurso == 'ops.indisp'
    assert notif.recurso_id is not None


# ── Caso 2: payload leva o mtv CRU (nunca 'IndispEnum.x') + datas ISO ──
#
# Cobre os três endpoints porque o `mtv` chega de origem diferente em
# cada handler (ver docstring do módulo).


async def test_create_payload_mtv_cru_e_datas_iso(
    client, session, users, token, trips
):
    _, other_user = users

    response = await client.post(
        '/indisp/',
        json=_payload(other_user.id, mtv='sde'),
        headers=auth(token),
    )
    assert response.status_code == HTTPStatus.CREATED

    notif = (await _notifs_indisp(session))[0]
    assert notif.payload['mtv'] == 'sde'
    assert notif.payload['date_start'] == FUTURO.isoformat()
    assert (
        notif.payload['date_end'] == (FUTURO + timedelta(days=3)).isoformat()
    )


async def test_update_payload_mtv_cru(client, session, existing_indisp, token):
    """O mtv chega ao PUT como `model_dump()` do schema — membro de
    Enum, não string — e só sai cru no payload por causa do
    `getattr(db_indisp.mtv, 'value', db_indisp.mtv)` do handler.
    """
    response = await client.put(
        f'/indisp/{existing_indisp.id}',
        json={'mtv': 'lic'},
        headers=auth(token),
    )
    assert response.status_code == HTTPStatus.OK

    notif = (
        await _notifs_indisp(session, tipo=NotifTipo.INDISP_ALTERADA.value)
    )[0]
    assert notif.payload['mtv'] == 'lic'


async def test_delete_payload_mtv_cru(client, session, existing_indisp, token):
    """No DELETE o mtv vem direto da coluna (já string) — sem Enum no
    meio do caminho, mas o contrato do payload é o mesmo dos outros dois.
    """
    response = await client.delete(
        f'/indisp/{existing_indisp.id}', headers=auth(token)
    )
    assert response.status_code == HTTPStatus.OK

    notif = (
        await _notifs_indisp(session, tipo=NotifTipo.INDISP_REMOVIDA.value)
    )[0]
    assert notif.payload['mtv'] == 'fer'
    assert notif.payload['date_start'] == FUTURO.isoformat()


# ── Caso 3: quem lança a própria não se autonotifica ─────────────────


async def test_tripulante_lanca_propria_nao_notifica(
    client, session, users, trips
):
    user, _ = users

    response = await client.post(
        '/indisp/',
        json=_payload(user.id),
        headers=auth(fatbird_token(user)),
    )
    assert response.status_code == HTTPStatus.CREATED

    assert await _count_notifs(session) == 0


# ── Caso 4: PUT com diff notifica; PUT idempotente não ───────────────


async def test_put_com_diff_gera_notif_alterada(
    client, session, existing_indisp, token
):
    response = await client.put(
        f'/indisp/{existing_indisp.id}',
        json={'obs': 'obs nova de verdade'},
        headers=auth(token),
    )
    assert response.status_code == HTTPStatus.OK

    notifs = await _notifs_indisp(
        session, tipo=NotifTipo.INDISP_ALTERADA.value
    )
    assert len(notifs) == 1


async def test_put_idempotente_nao_notifica(
    client, session, existing_indisp, token
):
    """Payload igual ao que já está salvo não é evento — vira ruído."""
    payload = {
        'date_start': existing_indisp.date_start.isoformat(),
        'date_end': existing_indisp.date_end.isoformat(),
        'mtv': existing_indisp.mtv,
        'obs': existing_indisp.obs,
    }

    response = await client.put(
        f'/indisp/{existing_indisp.id}', json=payload, headers=auth(token)
    )
    assert response.status_code == HTTPStatus.OK

    assert await _count_notifs(session) == 0


# ── Caso 5: DELETE notifica indisp.removida ──────────────────────────


async def test_delete_gera_notif_removida(
    client, session, existing_indisp, token
):
    response = await client.delete(
        f'/indisp/{existing_indisp.id}', headers=auth(token)
    )
    assert response.status_code == HTTPStatus.OK

    notifs = await _notifs_indisp(
        session, tipo=NotifTipo.INDISP_REMOVIDA.value
    )
    assert len(notifs) == 1
    assert notifs[0].user_id == existing_indisp.user_id


# ── Caso 6: mutação rejeitada não deixa notificação órfã ─────────────


async def test_create_invalido_nao_deixa_notif_orfa(
    client, session, users, token, trips
):
    """Período invertido é recusado antes de qualquer `notificar_usuarios`
    — a linha de notificações tem de continuar vazia depois da falha.
    """
    _, other_user = users

    payload = _payload(other_user.id)
    payload['date_start'], payload['date_end'] = (
        payload['date_end'],
        payload['date_start'],
    )

    response = await client.post('/indisp/', json=payload, headers=auth(token))
    assert response.status_code == HTTPStatus.BAD_REQUEST

    assert await _count_notifs(session) == 0


async def test_create_duplicado_nao_deixa_notif_orfa(
    client, session, users, token, trips
):
    user, other_user = users

    existente = IndispFactory(
        user_id=other_user.id,
        created_by=user.id,
        date_start=FUTURO,
        date_end=FUTURO + timedelta(days=3),
        mtv='sde',
    )
    session.add(existente)
    await session.commit()

    response = await client.post(
        '/indisp/', json=_payload(other_user.id), headers=auth(token)
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'já registrada' in response.json()['message']

    # A duplicata foi semeada direto pelo factory (sem passar pelo POST),
    # então nenhuma notificação existia antes da tentativa rejeitada.
    assert await _count_notifs(session) == 0


# ── Caso 7: segregação por app — só o FatBird vê o quadrinho de indisp ──


async def test_client_nao_ve_notif_de_indisp(
    client, session, users, token, trips
):
    """Audiência é 'tripulante': some da lista e do contador do client."""
    _, other_user = users

    response = await client.post(
        '/indisp/', json=_payload(other_user.id), headers=auth(token)
    )
    assert response.status_code == HTTPStatus.CREATED

    lista = await client.get('/notificacoes/', headers=auth(token))
    assert lista.json()['total'] == 0

    contador = await client.get('/notificacoes/contador', headers=auth(token))
    assert contador.json()['data'] == {
        'nao_lidas': 0,
        'tarefas': 0,
        'total': 0,
    }


async def test_fatbird_ve_notif_de_indisp(
    client, session, users, token, trips
):
    """...e o tripulante alvo vê a dele no portal."""
    _, other_user = users

    response = await client.post(
        '/indisp/', json=_payload(other_user.id), headers=auth(token)
    )
    assert response.status_code == HTTPStatus.CREATED

    lista = await client.get(
        '/notificacoes/', headers=auth(fatbird_token(other_user))
    )
    assert lista.json()['total'] == 1
    item = lista.json()['data'][0]
    assert item['tipo'] == NotifTipo.INDISP_CRIADA.value
