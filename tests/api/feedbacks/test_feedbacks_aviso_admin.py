"""Aviso à ADMINISTRAÇÃO: feedback novo e mensagem do autor chegam no
sino do client de cada admin de sistema.

`token_sistema` dá a `users[0]` o vínculo admin SEM organização — é ele o
admin de sistema destes testes. O autor é `users[1]` (fixture `autor`).
"""

from datetime import datetime, timezone
from http import HTTPStatus

import pytest
from sqlalchemy import select

from fcontrol_api.enums.notificacao import (
    NotifAudiencia,
    NotifEscopo,
    NotifTipo,
)
from fcontrol_api.models.shared.notificacao import Notificacao
from tests.api.notificacoes.conftest import auth, fatbird_token

pytestmark = pytest.mark.anyio

NOVO = {
    'tipo': 'bug',
    'titulo': 'Não abre',
    'descricao': 'A tela fica em branco ao abrir.',
}


async def _avisos(session, user_id):
    result = await session.scalars(
        select(Notificacao)
        .where(
            Notificacao.user_id == user_id,
            Notificacao.recurso == 'shared.feedback',
        )
        .order_by(Notificacao.id)
    )
    return result.all()


async def _mensagem_do_autor(client, autor, feedback_id, texto):
    response = await client.post(
        f'/feedbacks/{feedback_id}/mensagens',
        json={'texto': texto},
        headers=auth(fatbird_token(autor)),
    )
    assert response.status_code == HTTPStatus.CREATED
    return response


async def test_envio_avisa_admin_de_sistema(
    client, session, users, token_sistema, autor
):
    admin, _ = users

    response = await client.post(
        '/feedbacks/', json=NOVO, headers=auth(fatbird_token(autor))
    )

    assert response.status_code == HTTPStatus.CREATED
    feedback_id = response.json()['data']['id']
    [aviso] = await _avisos(session, admin.id)
    assert aviso.tipo == NotifTipo.FEEDBACK_RECEBIDO.value
    assert aviso.escopo == NotifEscopo.DIRETA.value
    # O painel da administração só existe no client, mesmo para feedback
    # que nasceu no FatBird.
    assert aviso.audiencia == NotifAudiencia.GESTOR.value
    assert aviso.recurso_id == feedback_id
    assert aviso.titulo == 'Novo feedback recebido'
    assert aviso.descricao == 'Não abre'
    assert aviso.created_by == autor.id
    assert await _avisos(session, autor.id) == []


async def test_admin_de_unidade_nao_e_avisado(
    client, session, users, token, autor
):
    # `token` dá a `users[0]` admin NA '11gt', não de sistema: a caixa
    # de feedbacks não é dele.
    admin_da_unidade, _ = users

    response = await client.post(
        '/feedbacks/', json=NOVO, headers=auth(fatbird_token(autor))
    )

    assert response.status_code == HTTPStatus.CREATED
    assert await _avisos(session, admin_da_unidade.id) == []


async def test_admin_de_sistema_autor_nao_se_avisa(
    client, session, users, token_sistema, token
):
    # `users[0]` é admin de sistema (`token_sistema`) e envia pelo client
    # com o token da unidade.
    admin, _ = users

    response = await client.post('/feedbacks/', json=NOVO, headers=auth(token))

    assert response.status_code == HTTPStatus.CREATED
    assert await _avisos(session, admin.id) == []


async def test_mensagens_do_autor_agrupam_num_aviso(
    client, session, users, token_sistema, autor, feedback
):
    admin, _ = users

    await _mensagem_do_autor(client, autor, feedback.id, 'Mais detalhe')
    await _mensagem_do_autor(client, autor, feedback.id, 'E outro')

    [aviso] = await _avisos(session, admin.id)
    assert aviso.tipo == NotifTipo.FEEDBACK_MENSAGEM_AUTOR.value
    assert aviso.payload == {'qtd': 2}
    assert aviso.titulo == '2 novas mensagens do autor'
    assert aviso.descricao == feedback.titulo


async def test_mensagem_sobre_feedback_nao_lido_so_renova_o_aviso(
    client, session, users, token_sistema, autor
):
    admin, _ = users
    response = await client.post(
        '/feedbacks/', json=NOVO, headers=auth(fatbird_token(autor))
    )
    feedback_id = response.json()['data']['id']
    [recebido] = await _avisos(session, admin.id)
    antes = recebido.created_at

    await _mensagem_do_autor(client, autor, feedback_id, 'Esqueci de dizer')

    await session.refresh(recebido)
    [aviso] = await _avisos(session, admin.id)
    assert aviso.id == recebido.id
    assert aviso.tipo == NotifTipo.FEEDBACK_RECEBIDO.value
    assert aviso.titulo == 'Novo feedback recebido'
    assert aviso.created_at > antes


async def test_com_aviso_lido_mensagem_do_autor_emite_novo(
    client, session, users, token_sistema, autor, feedback
):
    admin, _ = users
    await _mensagem_do_autor(client, autor, feedback.id, 'Primeira')
    [lido] = await _avisos(session, admin.id)
    lido.read_at = datetime.now(timezone.utc)
    await session.commit()

    await _mensagem_do_autor(client, autor, feedback.id, 'Segunda')

    avisos = await _avisos(session, admin.id)
    assert len(avisos) == 2
    assert avisos[1].read_at is None
    assert avisos[1].titulo == 'Nova mensagem do autor'
    assert avisos[1].payload == {'qtd': 1}
