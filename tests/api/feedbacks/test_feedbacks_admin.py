"""Lado da ADMINISTRAÇÃO: conversa, status, aviso ao autor e limpeza."""

from datetime import datetime, timezone
from http import HTTPStatus

import pytest
from sqlalchemy import func, select

from fcontrol_api.enums.notificacao import (
    NotifAudiencia,
    NotifEscopo,
    NotifTipo,
)
from fcontrol_api.models.shared.feedback import FeedbackEvento
from fcontrol_api.models.shared.notificacao import Notificacao
from tests.api.notificacoes.conftest import auth, fatbird_token

pytestmark = pytest.mark.anyio


async def _mensagem(client, token, feedback_id, texto, status=None):
    body = {'texto': texto}
    if status:
        body['status'] = status
    return await client.post(
        f'/admin/feedbacks/{feedback_id}/mensagens',
        json=body,
        headers=auth(token),
    )


async def _avisos(session, feedback_id):
    result = await session.scalars(
        select(Notificacao)
        .where(
            Notificacao.recurso == 'shared.feedback',
            Notificacao.recurso_id == feedback_id,
        )
        .order_by(Notificacao.id)
    )
    return result.all()


async def test_admin_le_a_conversa(client, token_sistema, feedback):
    response = await client.get(
        f'/admin/feedbacks/{feedback.id}', headers=auth(token_sistema)
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['data']['eventos'] == []


async def test_mensagem_do_admin_avisa_o_autor(
    client, session, users, token_sistema, autor, feedback
):
    admin, _ = users

    response = await _mensagem(
        client, token_sistema, feedback.id, 'Vamos corrigir.'
    )

    assert response.status_code == HTTPStatus.CREATED
    ultimo = response.json()['data']['eventos'][-1]
    assert ultimo['texto'] == 'Vamos corrigir.'
    assert ultimo['do_autor'] is False

    avisos = await _avisos(session, feedback.id)
    assert len(avisos) == 1
    aviso = avisos[0]
    assert aviso.user_id == autor.id
    assert aviso.escopo == NotifEscopo.DIRETA.value
    assert aviso.audiencia == NotifAudiencia.TRIPULANTE.value
    assert aviso.tipo == NotifTipo.FEEDBACK_MENSAGEM.value
    assert aviso.titulo == 'Nova mensagem no seu feedback'
    assert aviso.descricao == feedback.titulo
    assert aviso.payload == {'qtd': 1}
    assert aviso.uae == '11gt'
    assert aviso.created_by == admin.id


async def test_segunda_mensagem_com_aviso_nao_lido_agrupa(
    client, session, token_sistema, autor, feedback
):
    await _mensagem(client, token_sistema, feedback.id, 'Primeira')
    criado_em = (await _avisos(session, feedback.id))[0].created_at

    await _mensagem(client, token_sistema, feedback.id, 'Segunda')

    avisos = await _avisos(session, feedback.id)
    assert len(avisos) == 1
    assert avisos[0].payload == {'qtd': 2}
    assert avisos[0].titulo == '2 novas mensagens no seu feedback'
    # Volta ao topo do sino: o agrupamento reatribui `created_at`.
    assert avisos[0].created_at > criado_em


async def test_com_aviso_lido_emite_novo(
    client, session, token_sistema, autor, feedback
):
    await _mensagem(client, token_sistema, feedback.id, 'Primeira')
    lido = (await _avisos(session, feedback.id))[0]
    lido.read_at = datetime.now(timezone.utc)
    await session.commit()

    await _mensagem(client, token_sistema, feedback.id, 'Segunda')

    avisos = await _avisos(session, feedback.id)
    assert len(avisos) == 2
    assert avisos[1].payload == {'qtd': 1}
    assert avisos[1].read_at is None


async def test_mensagem_com_status_grava_os_dois_eventos(
    client, session, token_sistema, autor, feedback
):
    response = await _mensagem(
        client, token_sistema, feedback.id, 'Feito.', status='concluido'
    )

    data = response.json()['data']
    assert data['status'] == 'concluido'
    assert [e['tipo'] for e in data['eventos']] == ['mensagem', 'status']
    assert data['eventos'][1]['status'] == 'concluido'
    assert len(await _avisos(session, feedback.id)) == 1


async def test_mensagem_com_status_igual_nao_grava_evento_de_status(
    client, token_sistema, autor, feedback
):
    response = await _mensagem(
        client, token_sistema, feedback.id, 'Só um aviso', status='aberto'
    )

    tipos = [e['tipo'] for e in response.json()['data']['eventos']]
    assert tipos == ['mensagem']


async def test_patch_status_grava_evento_e_nao_avisa(
    client, session, token_sistema, autor, feedback
):
    response = await client.patch(
        f'/admin/feedbacks/{feedback.id}',
        json={'status': 'aceito'},
        headers=auth(token_sistema),
    )

    assert response.status_code == HTTPStatus.OK
    eventos = response.json()['data']['eventos']
    assert [(e['tipo'], e['status']) for e in eventos] == [
        ('status', 'aceito')
    ]
    assert await _avisos(session, feedback.id) == []


async def test_patch_status_igual_nao_grava_evento(
    client, token_sistema, autor, feedback
):
    response = await client.patch(
        f'/admin/feedbacks/{feedback.id}',
        json={'status': 'aberto'},
        headers=auth(token_sistema),
    )

    assert response.json()['data']['eventos'] == []


async def test_patch_sem_status_recebe_422(client, token_sistema, feedback):
    response = await client.patch(
        f'/admin/feedbacks/{feedback.id}',
        json={},
        headers=auth(token_sistema),
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_admin_no_proprio_feedback_nao_se_avisa(
    client, session, users, token_sistema, make_feedback
):
    admin, _ = users
    proprio = await make_feedback(admin)

    await _mensagem(client, token_sistema, proprio.id, 'Nota para mim')

    assert await _avisos(session, proprio.id) == []


async def test_mensagem_status_nao_conta_em_total_nem_em_atividade(
    client, session, token_sistema, autor, make_feedback
):
    """Cobertura extra pedida na revisão da Tarefa 2: um PATCH de status
    num feedback antigo não o faz subir na lista nem soma mensagem —
    `ultima_atividade` e `total_mensagens` só olham `tipo='mensagem'`."""
    antigo = await make_feedback(autor, titulo='Antigo')
    recente = await make_feedback(autor, titulo='Recente')

    response = await client.patch(
        f'/admin/feedbacks/{antigo.id}',
        json={'status': 'aceito'},
        headers=auth(token_sistema),
    )
    assert response.status_code == HTTPStatus.OK

    listagem = await client.get(
        '/admin/feedbacks/', headers=auth(token_sistema)
    )
    data = listagem.json()['data']
    item_antigo = next(f for f in data if f['id'] == antigo.id)
    item_recente = next(f for f in data if f['id'] == recente.id)

    assert item_antigo['total_mensagens'] == 0
    assert item_antigo['ultima_mensagem'] is None
    # `recente` foi criado depois: sem mensagem em nenhum dos dois, a
    # atividade continua ordenada pela criação — o PATCH de status não
    # promoveu `antigo` para o topo.
    assert data.index(item_recente) < data.index(item_antigo)


async def test_mensagem_em_feedback_de_origem_client_avisa_gestor(
    client, session, users, token_sistema, autor, make_feedback
):
    """Separação por app: feedback enviado pelo client avisa no sino DO
    client (audiência `gestor`), com o mesmo contrato do FatBird."""
    admin, _ = users
    do_client = await make_feedback(autor, origem='client')

    response = await _mensagem(
        client, token_sistema, do_client.id, 'Recebido, obrigado'
    )

    assert response.status_code == HTTPStatus.CREATED
    avisos = await _avisos(session, do_client.id)
    assert len(avisos) == 1
    aviso = avisos[0]
    assert aviso.user_id == autor.id
    assert aviso.escopo == NotifEscopo.DIRETA.value
    assert aviso.audiencia == NotifAudiencia.GESTOR.value
    assert aviso.tipo == NotifTipo.FEEDBACK_MENSAGEM.value
    assert aviso.titulo == 'Nova mensagem no seu feedback'
    assert aviso.descricao == do_client.titulo
    assert aviso.payload == {'qtd': 1}
    assert aviso.created_by == admin.id
    assert aviso.uae == do_client.uae


async def test_agrupamento_nao_mistura_audiencia(
    client, session, token_sistema, autor, make_feedback
):
    """A busca do aviso pendente para agrupar filtra por `audiencia`: um
    aviso `tripulante` não lido (resquício hipotético, ex. de uma origem
    trocada) não pode ser reaproveitado nem alterado quando a mensagem é
    de um feedback `client` — os dois nascem e ficam sem se tocar."""
    do_client = await make_feedback(autor, origem='client')
    tripulante_alheio = Notificacao(
        uae=do_client.uae,
        escopo=NotifEscopo.DIRETA.value,
        audiencia=NotifAudiencia.TRIPULANTE.value,
        tipo=NotifTipo.FEEDBACK_MENSAGEM.value,
        titulo='Nova mensagem no seu feedback',
        recurso='shared.feedback',
        recurso_id=do_client.id,
        user_id=autor.id,
        payload={'qtd': 1},
    )
    session.add(tripulante_alheio)
    await session.commit()

    await _mensagem(client, token_sistema, do_client.id, 'Oi')

    avisos = await _avisos(session, do_client.id)
    assert len(avisos) == 2
    tripulante = next(
        a for a in avisos if a.audiencia == NotifAudiencia.TRIPULANTE.value
    )
    gestor = next(
        a for a in avisos if a.audiencia == NotifAudiencia.GESTOR.value
    )
    # O `tripulante_alheio` não foi tocado: mesmo id, mesmo payload.
    assert tripulante.id == tripulante_alheio.id
    assert tripulante.payload == {'qtd': 1}
    assert tripulante.read_at is None
    # O `gestor` é um aviso NOVO (não incrementado a partir do tripulante).
    assert gestor.payload == {'qtd': 1}
    assert gestor.titulo == 'Nova mensagem no seu feedback'


async def test_segunda_mensagem_origem_client_tambem_agrupa(
    client, session, token_sistema, autor, make_feedback
):
    do_client = await make_feedback(autor, origem='client')
    await _mensagem(client, token_sistema, do_client.id, 'Primeira')

    await _mensagem(client, token_sistema, do_client.id, 'Segunda')

    avisos = await _avisos(session, do_client.id)
    assert len(avisos) == 1
    assert avisos[0].payload == {'qtd': 2}
    assert avisos[0].titulo == '2 novas mensagens no seu feedback'


async def test_aviso_de_feedback_segrega_por_app(
    client, session, autor, token_sistema, make_feedback, make_org_token
):
    """Token do client vê o aviso de origem `client` e não o de
    `fatbird`; o inverso vale para o token do FatBird — cada app só
    enxerga o sino da conversa que nasceu nele."""
    do_client = await make_feedback(
        autor, origem='client', titulo='Via client'
    )
    do_fatbird = await make_feedback(
        autor, origem='fatbird', titulo='Via FatBird'
    )

    await _mensagem(client, token_sistema, do_client.id, 'Oi (client)')
    await _mensagem(client, token_sistema, do_fatbird.id, 'Oi (fatbird)')

    aviso_client = (await _avisos(session, do_client.id))[0]
    aviso_fatbird = (await _avisos(session, do_fatbird.id))[0]

    token_client_autor = await make_org_token(autor, active_org='11gt')
    resposta_client = await client.get(
        '/notificacoes/', headers=auth(token_client_autor)
    )
    ids_no_client = {n['id'] for n in resposta_client.json()['data']}
    assert aviso_client.id in ids_no_client
    assert aviso_fatbird.id not in ids_no_client

    resposta_fatbird = await client.get(
        '/notificacoes/', headers=auth(fatbird_token(autor))
    )
    ids_no_fatbird = {n['id'] for n in resposta_fatbird.json()['data']}
    assert aviso_fatbird.id in ids_no_fatbird
    assert aviso_client.id not in ids_no_fatbird


async def test_excluir_apaga_conversa_e_so_os_avisos_dela(
    client, session, token_sistema, autor, feedback
):
    await _mensagem(client, token_sistema, feedback.id, 'Vamos ver')
    # Aviso de OUTRO recurso com o mesmo `recurso_id`: sem o filtro por
    # recurso, a limpeza o apagaria junto.
    alheio = Notificacao(
        uae='11gt',
        escopo=NotifEscopo.DIRETA.value,
        audiencia=NotifAudiencia.TRIPULANTE.value,
        tipo=NotifTipo.INDISP_CRIADA.value,
        titulo='Indisponibilidade',
        recurso='ops.indisp',
        recurso_id=feedback.id,
        user_id=autor.id,
    )
    session.add(alheio)
    await session.commit()

    response = await client.delete(
        f'/admin/feedbacks/{feedback.id}', headers=auth(token_sistema)
    )

    assert response.status_code == HTTPStatus.OK
    assert await _avisos(session, feedback.id) == []
    assert await session.get(Notificacao, alheio.id) is not None
    restantes = await session.scalar(
        select(func.count())
        .select_from(FeedbackEvento)
        .where(FeedbackEvento.feedback_id == feedback.id)
    )
    assert restantes == 0


async def test_lista_do_admin_traz_resumo(
    client, token_sistema, autor, feedback
):
    await _mensagem(client, token_sistema, feedback.id, 'Recebido')

    response = await client.get(
        '/admin/feedbacks/', headers=auth(token_sistema)
    )

    item = next(f for f in response.json()['data'] if f['id'] == feedback.id)
    assert item['total_mensagens'] == 1
    assert item['ultima_mensagem']['do_autor'] is False


@pytest.mark.parametrize(
    ('method', 'sufixo', 'body'),
    [
        ('GET', '', None),
        ('POST', '/mensagens', {'texto': 'x'}),
    ],
)
async def test_rotas_novas_exigem_contexto_sistema(
    client, token, feedback, method, sufixo, body
):
    response = await client.request(
        method,
        f'/admin/feedbacks/{feedback.id}{sufixo}',
        json=body,
        headers=auth(token),
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
