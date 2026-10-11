"""Testes do router de administração de sistema `/projetos`.

O catálogo de projetos/modelos de aeronave é global (control-plane): o router
inteiro aplica `require_system_admin`. Só o admin de SISTEMA (contexto
Sistema, `active_org` NULL — a fixture `token_sistema`) acessa; o admin de
unidade (`token`, admin escopado na '11gt') e quem não tem permissão
(`token_sem_perm`) recebem 403 `SCOPE_FORBIDDEN`, inclusive no GET.

Seed: 'C8' (KC-390) e 'C1' (C-130), ambos associados a um tenant
em `tenant_projetos`. Os ids/modelos criados aqui são novos (`Z9`, `Y9`...).
A caixa do modelo seedado não é comparada com literal: a migration ainda o
grava em minúsculas, diferente de produção (ver `docs/ai/notes/dominio.md`),
então os asserts comparam o modelo lido antes com o lido depois.

Atenção à sessão compartilhada: quando a rota captura `IntegrityError`, o
`session.rollback()` dela desfaz a transação externa do teste (inclusive as
linhas criadas pelo próprio teste). Por isso, nos casos de 409 os asserts de
"nada mudou" usam linhas do seed e a mensagem do erro.
"""

from http import HTTPStatus

import pytest
from sqlalchemy import func, select

from fcontrol_api.models.shared.aeronaves import (
    Aeronave,
    ProjetoAnv,
    TenantProjeto,
)
from fcontrol_api.models.shared.tripulantes import Tripulante
from tests.factories import TripFactory

pytestmark = pytest.mark.anyio

# Id e modelo de um projeto novo, sem vínculo algum.
NOVO_ID = 'Z9'
NOVO_MODELO = 'ZZ-9'


def bearer(token):
    return {'Authorization': f'Bearer {token}'}


async def _projeto(session, id_projeto):
    """Relê o projeto do banco (ignora o identity map da sessão)."""
    return await session.scalar(
        select(ProjetoAnv)
        .where(ProjetoAnv.id_projeto == id_projeto)
        .execution_options(populate_existing=True)
    )


async def _total(session):
    return await session.scalar(select(func.count()).select_from(ProjetoAnv))


@pytest.fixture
async def projeto_novo(session):
    """Projeto sem nenhum vínculo (tenant, aeronave, tripulante)."""
    projeto = ProjetoAnv(id_projeto=NOVO_ID, modelo=NOVO_MODELO)
    session.add(projeto)
    await session.commit()
    return projeto


# ========================================
# Gate: require_system_admin no router inteiro
# ========================================

# (método, url, corpo). Os corpos são válidos: o 403 vem do gate, nunca
# de um 422 que mascararia a ausência dele.
ROTAS = [
    ('GET', '/projetos/', None),
    ('POST', '/projetos/', {'id_projeto': 'Y9', 'modelo': 'YY-9'}),
    ('PUT', '/projetos/C1', {'modelo': 'OUTRO'}),
    ('DELETE', '/projetos/C1', None),
]


@pytest.mark.parametrize(('method', 'url', 'body'), ROTAS)
async def test_admin_de_unidade_recebe_403(client, token, method, url, body):
    """Admin escopado na '11gt' não administra o catálogo global."""
    response = await client.request(
        method, url, json=body, headers=bearer(token)
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json()['message'] == 'SCOPE_FORBIDDEN'


@pytest.mark.parametrize(('method', 'url', 'body'), ROTAS)
async def test_sem_permissao_recebe_403(
    client, token_sem_perm, method, url, body
):
    response = await client.request(
        method, url, json=body, headers=bearer(token_sem_perm)
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json()['message'] == 'SCOPE_FORBIDDEN'


@pytest.mark.parametrize(('method', 'url', 'body'), ROTAS)
async def test_sem_token_recebe_401(client, method, url, body):
    response = await client.request(method, url, json=body)

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_gate_nao_altera_o_banco(
    client, session, token, token_sem_perm, projeto_novo
):
    """Escritas barradas no gate não criam, editam nem removem nada."""
    for tok in (token, token_sem_perm):
        post = await client.post(
            '/projetos/',
            json={'id_projeto': 'Y9', 'modelo': 'YY-9'},
            headers=bearer(tok),
        )
        put = await client.put(
            f'/projetos/{NOVO_ID}',
            json={'modelo': 'RENOMEADO'},
            headers=bearer(tok),
        )
        delete = await client.delete(
            f'/projetos/{NOVO_ID}', headers=bearer(tok)
        )
        assert {post.status_code, put.status_code, delete.status_code} == {
            HTTPStatus.FORBIDDEN
        }

    assert await _projeto(session, 'Y9') is None
    existente = await _projeto(session, NOVO_ID)
    assert existente is not None
    assert existente.modelo == NOVO_MODELO


# ========================================
# GET /projetos/
# ========================================


async def test_list_projetos_ok(client, session, token_sistema):
    response = await client.get('/projetos/', headers=bearer(token_sistema))

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    por_id = {p['id_projeto']: p['modelo'] for p in data}
    for id_projeto in ('C8', 'C1'):
        assert (
            por_id[id_projeto] == (await _projeto(session, id_projeto)).modelo
        )


async def test_list_projetos_ordenado_por_modelo(client, token_sistema):
    # A ordem por id (Y1, Y2), a de inserção (Y1, Y2) e a por modelo
    # (Y2, Y1) divergem: só a ordenação por modelo põe AAA-1 primeiro.
    for id_projeto, modelo in (('Y1', 'AAA-2'), ('Y2', 'AAA-1')):
        criado = await client.post(
            '/projetos/',
            json={'id_projeto': id_projeto, 'modelo': modelo},
            headers=bearer(token_sistema),
        )
        assert criado.status_code == HTTPStatus.CREATED

    response = await client.get('/projetos/', headers=bearer(token_sistema))

    modelos = [p['modelo'] for p in response.json()['data']]
    assert modelos.index('AAA-1') < modelos.index('AAA-2')


# ========================================
# POST /projetos/
# ========================================


async def test_create_projeto_ok(client, session, token_sistema):
    response = await client.post(
        '/projetos/',
        json={'id_projeto': NOVO_ID, 'modelo': NOVO_MODELO},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()
    assert body['message'] == 'Projeto cadastrado com sucesso'
    assert body['data'] == {'id_projeto': NOVO_ID, 'modelo': NOVO_MODELO}
    projeto = await _projeto(session, NOVO_ID)
    assert projeto.modelo == NOVO_MODELO


async def test_create_projeto_normaliza_caixa_alta_e_espacos(
    client, session, token_sistema
):
    response = await client.post(
        '/projetos/',
        json={'id_projeto': ' z9 ', 'modelo': '  kc-777 '},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()['data'] == {
        'id_projeto': 'Z9',
        'modelo': 'KC-777',
    }
    assert (await _projeto(session, 'Z9')).modelo == 'KC-777'
    assert await _projeto(session, 'z9') is None


async def test_create_projeto_id_duplicado_409(client, session, token_sistema):
    antes = (await _projeto(session, 'C8')).modelo
    response = await client.post(
        '/projetos/',
        json={'id_projeto': 'C8', 'modelo': 'OUTRO-1'},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert 'identificador' in response.json()['message']
    assert (await _projeto(session, 'C8')).modelo == antes


async def test_create_projeto_id_duplicado_em_minusculas_409(
    client, session, token_sistema
):
    """A normalização para caixa alta faz 'c8' colidir com o 'C8'."""
    antes = (await _projeto(session, 'C8')).modelo
    response = await client.post(
        '/projetos/',
        json={'id_projeto': 'c8', 'modelo': 'OUTRO-1'},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert 'identificador' in response.json()['message']
    assert (await _projeto(session, 'C8')).modelo == antes


async def test_create_projeto_modelo_duplicado_409(client, token_sistema):
    """Id novo com modelo já cadastrado: UNIQUE em `modelo` → 409."""
    criado = await client.post(
        '/projetos/',
        json={'id_projeto': NOVO_ID, 'modelo': NOVO_MODELO},
        headers=bearer(token_sistema),
    )
    assert criado.status_code == HTTPStatus.CREATED

    response = await client.post(
        '/projetos/',
        json={'id_projeto': 'Y9', 'modelo': NOVO_MODELO.lower()},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert 'modelo' in response.json()['message']


@pytest.mark.parametrize(
    'body',
    [
        {'id_projeto': 'ABC', 'modelo': 'X-1'},
        {'id_projeto': 'A', 'modelo': 'X-1'},
        {'id_projeto': 'a ', 'modelo': 'X-1'},
        {'id_projeto': 'Y9', 'modelo': ''},
        {'id_projeto': 'Y9', 'modelo': '   '},
        {'id_projeto': 'Y9', 'modelo': 'X' * 21},
        {'id_projeto': 'Y9'},
        {'modelo': 'X-1'},
    ],
    ids=[
        'id-longo',
        'id-curto',
        'id-curto-apos-strip',
        'modelo-vazio',
        'modelo-so-espacos',
        'modelo-longo',
        'sem-modelo',
        'sem-id',
    ],
)
async def test_create_projeto_payload_invalido_422(
    client, session, token_sistema, body
):
    antes = await _total(session)

    response = await client.post(
        '/projetos/', json=body, headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert await _total(session) == antes


# ========================================
# PUT /projetos/{id_projeto}
# ========================================


async def test_update_projeto_ok_normaliza_caixa_alta(
    client, session, token_sistema, projeto_novo
):
    response = await client.put(
        f'/projetos/{NOVO_ID}',
        json={'modelo': ' novo-modelo '},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body['message'] == 'Projeto atualizado com sucesso'
    assert body['data'] == {'id_projeto': NOVO_ID, 'modelo': 'NOVO-MODELO'}
    assert (await _projeto(session, NOVO_ID)).modelo == 'NOVO-MODELO'


async def test_update_projeto_mesmo_modelo_nao_conflita(
    client, token_sistema, projeto_novo
):
    """Regravar o próprio modelo não é duplicata."""
    response = await client.put(
        f'/projetos/{NOVO_ID}',
        json={'modelo': NOVO_MODELO},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['data']['modelo'] == NOVO_MODELO


async def test_update_projeto_id_projeto_no_corpo_422_e_nada_renomeado(
    client, session, token_sistema, projeto_novo
):
    """O id é a PK e vem da URL: `id_projeto` no corpo é recusado (422),
    não ignorado em silêncio, e nem o id nem o modelo mudam."""
    response = await client.put(
        f'/projetos/{NOVO_ID}',
        json={'id_projeto': 'Y9', 'modelo': 'NOVO-MODELO'},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert 'body.id_projeto' in response.json()['errors']
    assert await _projeto(session, 'Y9') is None
    assert (await _projeto(session, NOVO_ID)).modelo == NOVO_MODELO


async def test_update_projeto_acha_id_em_minusculas_na_url(
    client, session, token_sistema, projeto_novo
):
    """O id é gravado em caixa alta: `z9` na URL acha o `Z9`."""
    response = await client.put(
        f'/projetos/{NOVO_ID.lower()}',
        json={'modelo': 'novo-modelo'},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['data'] == {
        'id_projeto': NOVO_ID,
        'modelo': 'NOVO-MODELO',
    }
    assert (await _projeto(session, NOVO_ID)).modelo == 'NOVO-MODELO'


async def test_update_projeto_propaga_modelo_para_tripulantes(
    client, session, users, token_sistema, projeto_novo
):
    """`tripulantes.proj` é FK para `modelo` com ON UPDATE CASCADE."""
    user, _ = users
    trip = TripFactory(user_id=user.id, uae='11gt', proj=NOVO_MODELO)
    session.add(trip)
    await session.commit()

    response = await client.put(
        f'/projetos/{NOVO_ID}',
        json={'modelo': 'ZZ-10'},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.OK
    proj = await session.scalar(
        select(Tripulante.proj)
        .where(Tripulante.id == trip.id)
        .execution_options(populate_existing=True)
    )
    assert proj == 'ZZ-10'


async def test_update_projeto_inexistente_404(client, token_sistema):
    response = await client.put(
        '/projetos/Y9',
        json={'modelo': 'X-1'},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Projeto não encontrado'


async def test_update_projeto_modelo_duplicado_409(
    client, session, token_sistema
):
    """Renomear para o modelo de outro projeto (em minúsculas, que o
    schema normaliza): UNIQUE → 409, e o C1 fica como estava."""
    antes = (await _projeto(session, 'C1')).modelo
    criado = await client.post(
        '/projetos/',
        json={'id_projeto': 'Y9', 'modelo': 'YY-9'},
        headers=bearer(token_sistema),
    )
    assert criado.status_code == HTTPStatus.CREATED

    response = await client.put(
        '/projetos/C1',
        json={'modelo': 'yy-9'},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert 'modelo' in response.json()['message']
    assert (await _projeto(session, 'C1')).modelo == antes


@pytest.mark.parametrize('modelo', ['', '   ', 'X' * 21])
async def test_update_projeto_modelo_invalido_422(
    client, session, token_sistema, modelo
):
    antes = (await _projeto(session, 'C1')).modelo
    response = await client.put(
        '/projetos/C1',
        json={'modelo': modelo},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert (await _projeto(session, 'C1')).modelo == antes


# ========================================
# DELETE /projetos/{id_projeto}
# ========================================


async def test_delete_projeto_ok(client, session, token_sistema, projeto_novo):
    response = await client.delete(
        f'/projetos/{NOVO_ID}', headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['message'] == 'Projeto removido com sucesso'
    assert await _projeto(session, NOVO_ID) is None
    # Só ele saiu: o seed continua inteiro.
    assert await _projeto(session, 'C8') is not None
    assert await _projeto(session, 'C1') is not None


async def test_delete_projeto_acha_id_em_minusculas_na_url(
    client, session, token_sistema, projeto_novo
):
    response = await client.delete(
        f'/projetos/{NOVO_ID.lower()}', headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.OK
    assert await _projeto(session, NOVO_ID) is None


async def test_delete_projeto_inexistente_404(client, token_sistema):
    response = await client.delete(
        '/projetos/Y9', headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Projeto não encontrado'


@pytest.mark.parametrize('id_projeto', ['C8', 'C1'])
async def test_delete_projeto_associado_a_tenant_409(
    client, session, token_sistema, id_projeto
):
    """Projeto operado por um tenant (`tenant_projetos`) não é removido."""
    response = await client.delete(
        f'/projetos/{id_projeto}', headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert 'em uso' in response.json()['message']
    assert await _projeto(session, id_projeto) is not None
    vinculo = await session.scalar(
        select(TenantProjeto)
        .where(TenantProjeto.projeto == id_projeto)
        .execution_options(populate_existing=True)
    )
    assert vinculo is not None


async def test_delete_projeto_com_aeronave_409(
    client, session, token_sistema, projeto_novo
):
    """Sem vínculo de tenant, só a aeronave (FK) segura o projeto."""
    session.add(
        Aeronave(
            matricula='9990',
            active=True,
            sit='DI',
            obs=None,
            projeto=NOVO_ID,
        )
    )
    await session.commit()

    response = await client.delete(
        f'/projetos/{NOVO_ID}', headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert 'em uso' in response.json()['message']


async def test_delete_projeto_com_tripulante_409(
    client, session, users, token_sistema, projeto_novo
):
    """Sem tenant nem aeronave, só o tripulante (FK por `modelo`) segura."""
    user, _ = users
    session.add(TripFactory(user_id=user.id, uae='11gt', proj=NOVO_MODELO))
    await session.commit()

    response = await client.delete(
        f'/projetos/{NOVO_ID}', headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert 'tripulantes' in response.json()['message']
