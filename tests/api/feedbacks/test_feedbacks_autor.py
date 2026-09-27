"""Lado do AUTOR: ler a própria conversa e escrever nela."""

from http import HTTPStatus

import pytest
from sqlalchemy import func, select

from fcontrol_api.models.shared.feedback import FeedbackEvento
from fcontrol_api.models.shared.notificacao import Notificacao
from tests.api.notificacoes.conftest import auth, fatbird_token

pytestmark = pytest.mark.anyio


async def _enviar(client, user, feedback_id, texto):
    return await client.post(
        f'/feedbacks/{feedback_id}/mensagens',
        json={'texto': texto},
        headers=auth(fatbird_token(user)),
    )


async def test_dono_le_a_propria_conversa(client, autor, feedback):
    response = await client.get(
        f'/feedbacks/{feedback.id}', headers=auth(fatbird_token(autor))
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert data['id'] == feedback.id
    assert data['eventos'] == []
    assert data['total_mensagens'] == 0
    assert data['ultima_mensagem'] is None


async def test_outro_usuario_recebe_404(client, token, autor, make_feedback):
    # `token` é do `users[0]`, no MESMO app (`client`) do feedback: isola
    # a variável dono da de origem — com o default `origem='fatbird'` o
    # 404 viria do filtro de app mesmo sem checar o dono.
    do_client = await make_feedback(autor, origem='client')

    response = await client.get(
        f'/feedbacks/{do_client.id}', headers=auth(token)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Feedback não encontrado'


async def test_inexistente_recebe_o_mesmo_404(client, autor, feedback):
    response = await client.get(
        '/feedbacks/999999', headers=auth(fatbird_token(autor))
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Feedback não encontrado'


async def test_autor_envia_mensagem(client, autor, feedback):
    response = await _enviar(client, autor, feedback.id, '  Mais detalhe  ')

    assert response.status_code == HTTPStatus.CREATED
    evento = response.json()['data']
    assert evento['tipo'] == 'mensagem'
    assert evento['texto'] == 'Mais detalhe'
    assert evento['status'] is None
    assert evento['do_autor'] is True
    assert evento['autor']['id'] == autor.id


async def test_mensagem_so_de_espacos_recebe_422(client, autor, feedback):
    response = await _enviar(client, autor, feedback.id, '   ')

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_mensagem_do_autor_nao_avisa_o_autor(
    client, session, autor, feedback
):
    # O aviso é da administração (`test_feedbacks_aviso_admin.py`): quem
    # escreveu nunca recebe aviso da própria mensagem.
    response = await _enviar(client, autor, feedback.id, 'Alguma novidade?')

    assert response.status_code == HTTPStatus.CREATED
    total = await session.scalar(
        select(func.count())
        .select_from(Notificacao)
        .where(
            Notificacao.recurso == 'shared.feedback',
            Notificacao.user_id == autor.id,
        )
    )
    assert total == 0


@pytest.mark.parametrize('status', ['concluido', 'recusado'])
async def test_conversa_encerrada_recusa_mensagem(
    client, session, autor, make_feedback, status
):
    encerrado = await make_feedback(autor, status=status)

    response = await _enviar(client, autor, encerrado.id, 'Ainda acontece')

    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()['message'] == 'Esta conversa foi encerrada'
    total = await session.scalar(
        select(func.count())
        .select_from(FeedbackEvento)
        .where(FeedbackEvento.feedback_id == encerrado.id)
    )
    assert total == 0


async def test_mensagem_em_feedback_alheio_recebe_404(
    client, token, autor, make_feedback
):
    # `token` é do `users[0]`, no MESMO app (`client`) do feedback:
    # qualquer autenticado alcança o endpoint; é o filtro por dono que
    # devolve 404 aqui (a origem já está igualada, então não é ela quem
    # discrimina o teste).
    do_client = await make_feedback(autor, origem='client')

    response = await client.post(
        f'/feedbacks/{do_client.id}/mensagens',
        json={'texto': 'Invasão'},
        headers=auth(token),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Feedback não encontrado'


async def test_lista_traz_resumo_e_ordena_por_atividade(
    client, autor, make_feedback
):
    antigo = await make_feedback(autor, titulo='Antigo')
    novo = await make_feedback(autor, titulo='Novo')
    await _enviar(client, autor, antigo.id, 'Retomando este')

    response = await client.get(
        '/feedbacks/me', headers=auth(fatbird_token(autor))
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert [f['id'] for f in data] == [antigo.id, novo.id]
    assert data[0]['total_mensagens'] == 1
    assert data[0]['ultima_mensagem']['texto'] == 'Retomando este'
    assert data[0]['ultima_mensagem']['do_autor'] is True
    assert data[1]['total_mensagens'] == 0
    assert data[1]['ultima_mensagem'] is None
    assert 'eventos' not in data[0]


# --- Separação por app: `origem` derivada do `app_client` do token -----


async def test_envio_pelo_fatbird_grava_origem_fatbird(client, autor):
    response = await client.post(
        '/feedbacks/',
        json={
            'tipo': 'bug',
            'titulo': 'Não abre',
            'descricao': 'A tela fica em branco ao abrir.',
        },
        headers=auth(fatbird_token(autor)),
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()['data']['origem'] == 'fatbird'


async def test_envio_pelo_client_grava_origem_client(client, token):
    response = await client.post(
        '/feedbacks/',
        json={
            'tipo': 'sugestao',
            'titulo': 'Poderia ter filtro',
            'descricao': 'Faltou um filtro por unidade na tela.',
        },
        headers=auth(token),
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()['data']['origem'] == 'client'


async def test_me_do_fatbird_nao_lista_feedback_de_origem_client(
    client, autor, make_feedback, make_token
):
    do_client = await make_feedback(autor, origem='client')
    do_fatbird = await make_feedback(autor, origem='fatbird')

    resposta_fatbird = await client.get(
        '/feedbacks/me', headers=auth(fatbird_token(autor))
    )
    ids_fatbird = [f['id'] for f in resposta_fatbird.json()['data']]
    assert do_fatbird.id in ids_fatbird
    assert do_client.id not in ids_fatbird

    token_client = await make_token(autor, client_id='test-client')
    resposta_client = await client.get(
        '/feedbacks/me', headers=auth(token_client)
    )
    ids_client = [f['id'] for f in resposta_client.json()['data']]
    assert do_client.id in ids_client
    assert do_fatbird.id not in ids_client


async def test_get_de_outro_app_recebe_404(
    client, autor, feedback, make_token
):
    # `feedback` é `origem='fatbird'` (default); um token do client do
    # mesmo autor recebe o mesmo 404 de inexistente.
    token_client = await make_token(autor, client_id='test-client')

    response = await client.get(
        f'/feedbacks/{feedback.id}', headers=auth(token_client)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Feedback não encontrado'


async def test_mensagem_de_outro_app_recebe_404(
    client, autor, feedback, make_token
):
    # Mesmo autor, app diferente: `feedback` é `origem='fatbird'` e o
    # token aqui é do client — o filtro por `origem` barra antes de
    # chegar no de dono.
    token_client = await make_token(autor, client_id='test-client')

    response = await client.post(
        f'/feedbacks/{feedback.id}/mensagens',
        json={'texto': 'Invasão de app'},
        headers=auth(token_client),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Feedback não encontrado'
