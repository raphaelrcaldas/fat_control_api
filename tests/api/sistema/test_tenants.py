"""Router `/tenants` (organizações clientes da plataforma).

Contrato fixado aqui:

- `GET /` é aberto a qualquer autenticado (tema e saudação por organização);
- todas as demais rotas — escrita do tenant e as três de
  `/{organizacao_id}/projetos`, inclusive a LISTAGEM — exigem admin de
  SISTEMA (`require_system_admin`). Admin de unidade (`token`) e usuário sem
  permissão (`token_sem_perm`) levam 403 `SCOPE_FORBIDDEN`; sem token, 401.

Escritas usam siglas novas (`zzt*`) para não mexer nos tenants do seed, que
são referenciados por usuários, tripulantes e aeronaves; o seed ('11gt'→C8,
'1gt'→C1) serve de testemunha de que nada vazou para outro tenant. O client
de teste compartilha a sessão: as leituras de verificação usam
`populate_existing` para não confundir identity map com banco.
"""

from http import HTTPStatus

import pytest
from sqlalchemy import func, select

from fcontrol_api.models.security.resources import Roles, UserRole
from fcontrol_api.models.shared.aeronaves import ProjetoAnv, TenantProjeto
from fcontrol_api.models.shared.funcoes import FuncaoUae
from fcontrol_api.models.shared.organizacao import Organizacao
from fcontrol_api.models.shared.tenant import Tenant

pytestmark = pytest.mark.anyio

URL = '/tenants/'
TEN = 'zztenant'  # tenant pré-existente, associado ao projeto C8
ORG = 'zzorgsolta'  # organização do diretório que NÃO é tenant


def bearer(token):
    return {'Authorization': f'Bearer {token}'}


async def buscar_tenant(session, organizacao_id):
    return await session.scalar(
        select(Tenant)
        .where(Tenant.organizacao_id == organizacao_id)
        .execution_options(populate_existing=True)
    )


async def n_tenants(session):
    return await session.scalar(select(func.count(Tenant.organizacao_id)))


async def modelo_de(session, id_projeto):
    """Modelo do projeto no banco: a migration semeia minúsculo e produção
    é maiúsculo (`docs/ai/notes/dominio.md`), então não se crava literal."""
    return await session.scalar(
        select(ProjetoAnv.modelo)
        .where(ProjetoAnv.id_projeto == id_projeto)
        .execution_options(populate_existing=True)
    )


async def role_existente(session):
    return await session.scalar(select(Roles.id).order_by(Roles.id).limit(1))


async def projetos_de(session, uae):
    rows = await session.scalars(
        select(TenantProjeto.projeto).where(TenantProjeto.uae == uae)
    )
    return sorted(rows)


@pytest.fixture
async def cenario(session):
    """Tenant `TEN` (com C8) e organização avulsa `ORG` (não é tenant)."""
    session.add_all([
        Organizacao(sigla=TEN, nome='Tenant de Teste'),
        Organizacao(sigla=ORG, nome='Organizacao Avulsa'),
    ])
    await session.flush()
    session.add(Tenant(organizacao_id=TEN))
    await session.flush()
    session.add(TenantProjeto(uae=TEN, projeto='C8'))
    await session.commit()


# ---------------------------------------------------------------- gate

# (método, url, corpo) — todas as rotas exceto `GET /`
GATED = [
    ('POST', URL, {'organizacao_id': ORG}),
    ('PATCH', f'{URL}{TEN}', {'active': False, 'tema': 'blue'}),
    ('DELETE', f'{URL}{TEN}', None),
    ('GET', f'{URL}{TEN}/projetos', None),
    ('POST', f'{URL}{TEN}/projetos', {'projeto': 'C1'}),
    ('DELETE', f'{URL}{TEN}/projetos/C8', None),
]


async def _assert_barrada(client, session, tk, method, url, body):
    tenants_antes = await n_tenants(session)

    response = await client.request(method, url, json=body, headers=bearer(tk))

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json()['message'] == 'SCOPE_FORBIDDEN'

    assert await n_tenants(session) == tenants_antes
    assert await buscar_tenant(session, ORG) is None
    tenant = await buscar_tenant(session, TEN)
    assert tenant is not None
    assert tenant.active is True
    assert tenant.tema == 'red'
    assert await projetos_de(session, TEN) == ['C8']


@pytest.mark.parametrize(('method', 'url', 'body'), GATED)
async def test_rota_barrada_para_admin_de_unidade(
    client, session, cenario, token, method, url, body
):
    """Admin da '11gt' não administra tenants: 403 e banco intacto."""
    await _assert_barrada(client, session, token, method, url, body)


@pytest.mark.parametrize(('method', 'url', 'body'), GATED)
async def test_rota_barrada_sem_permissao(
    client, session, cenario, token_sem_perm, method, url, body
):
    await _assert_barrada(client, session, token_sem_perm, method, url, body)


@pytest.mark.parametrize(('method', 'url', 'body'), GATED)
async def test_rota_sem_token_401(client, method, url, body):
    response = await client.request(method, url, json=body)

    assert response.status_code == HTTPStatus.UNAUTHORIZED


# --------------------------------------------------------- leitura aberta


async def test_list_aberta_a_autenticado_sem_permissao(client, token_sem_perm):
    """Contrato atual: sem gate — qualquer autenticado lista os tenants."""
    response = await client.get(URL, headers=bearer(token_sem_perm))

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    ids = [t['organizacao_id'] for t in data]
    assert {'11gt', '1gt'} <= set(ids)
    tenant = next(t for t in data if t['organizacao_id'] == '11gt')
    assert set(tenant) == {
        'organizacao_id',
        'active',
        'tema',
        'saudacao',
        'created_at',
        'organizacao',
    }
    assert tenant['active'] is True
    assert tenant['tema'] == 'red'
    assert tenant['organizacao']['sigla'] == '11gt'


async def test_list_ordenada_por_organizacao_id(
    client, session, cenario, token_sem_perm
):
    """`cenario` já inseriu 'zztenant'; '0zz' entra depois dele e ambos
    depois do seed. A ordem de inserção contradiz a de sigla, então só
    `ORDER BY organizacao_id` produz o resultado esperado."""
    session.add(Organizacao(sigla='0zz', nome='Primeiro Tenant'))
    await session.flush()
    session.add(Tenant(organizacao_id='0zz'))
    await session.commit()

    response = await client.get(URL, headers=bearer(token_sem_perm))

    ids = [t['organizacao_id'] for t in response.json()['data']]
    assert [i for i in ids if i in {'0zz', '11gt', '1gt', TEN}] == [
        '0zz',
        '11gt',
        '1gt',
        TEN,
    ]
    assert ids == sorted(ids)


async def test_list_sem_token_401(client):
    response = await client.get(URL)

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_list_nao_inclui_organizacao_que_nao_e_tenant(
    client, cenario, token_sem_perm
):
    response = await client.get(URL, headers=bearer(token_sem_perm))

    ids = [t['organizacao_id'] for t in response.json()['data']]
    assert TEN in ids
    assert ORG not in ids


# ------------------------------------------------------------- CRUD feliz


async def test_create_ok(client, session, cenario, token_sistema):
    response = await client.post(
        URL, json={'organizacao_id': ORG}, headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()
    assert body['message'] == 'Tenant registrado com sucesso'
    data = body['data']
    assert data['organizacao_id'] == ORG
    assert data['active'] is True
    assert data['tema'] == 'red'
    assert len(data['saudacao']) == 0
    assert data['organizacao']['nome'] == 'Organizacao Avulsa'

    assert await buscar_tenant(session, ORG) is not None


async def test_update_campos(client, session, cenario, token_sistema):
    response = await client.patch(
        f'{URL}{TEN}',
        json={'active': False, 'tema': 'blue', 'saudacao': 'Voar para vencer'},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body['message'] == 'Tenant atualizado com sucesso'
    assert body['data']['active'] is False
    assert body['data']['tema'] == 'blue'

    tenant = await buscar_tenant(session, TEN)
    assert tenant.active is False
    assert tenant.tema == 'blue'
    assert tenant.saudacao == 'Voar para vencer'


async def test_update_parcial_preserva_demais_campos(
    client, session, cenario, token_sistema
):
    await client.patch(
        f'{URL}{TEN}',
        json={'tema': 'indigo', 'saudacao': 'Lema'},
        headers=bearer(token_sistema),
    )

    response = await client.patch(
        f'{URL}{TEN}', json={'active': False}, headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.OK
    tenant = await buscar_tenant(session, TEN)
    assert tenant.active is False
    assert tenant.tema == 'indigo'
    assert tenant.saudacao == 'Lema'


async def test_update_saudacao_vazia_limpa(
    client, session, cenario, token_sistema
):
    """Limpar a saudação é enviar '' (None é ignorado)."""
    await client.patch(
        f'{URL}{TEN}', json={'saudacao': 'Lema'}, headers=bearer(token_sistema)
    )

    response = await client.patch(
        f'{URL}{TEN}', json={'saudacao': ''}, headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.OK
    assert len((await buscar_tenant(session, TEN)).saudacao) == 0


@pytest.mark.parametrize(
    'body',
    [
        {'active': None},
        {'tema': None},
        {'saudacao': None},
        {'active': None, 'tema': None, 'saudacao': None},
        {},
    ],
)
async def test_update_none_explicito_nao_altera_nem_estoura(
    client, session, cenario, token_sistema, body
):
    """Colunas NOT NULL: `null` significa "não alterar", não "setar None"."""
    await client.patch(
        f'{URL}{TEN}',
        json={'tema': 'blue', 'saudacao': 'Lema'},
        headers=bearer(token_sistema),
    )

    response = await client.patch(
        f'{URL}{TEN}', json=body, headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.OK
    tenant = await buscar_tenant(session, TEN)
    assert tenant.active is True
    assert tenant.tema == 'blue'
    assert tenant.saudacao == 'Lema'


async def test_delete_ok_remove_tenant_e_associacoes_mas_nao_a_org(
    client, session, cenario, token_sistema
):
    response = await client.delete(
        f'{URL}{TEN}', headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['message'] == 'Tenant removido com sucesso'
    assert await buscar_tenant(session, TEN) is None
    # associações caem em cascata; a org continua no diretório
    assert await projetos_de(session, TEN) == []
    assert await session.get(Organizacao, TEN) is not None
    # testemunha: tenants do seed intactos
    assert await projetos_de(session, '11gt') == ['C8']


async def test_list_projetos(client, session, cenario, token_sistema):
    response = await client.get(
        f'{URL}{TEN}/projetos', headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['data'] == [
        {'id_projeto': 'C8', 'modelo': await modelo_de(session, 'C8')}
    ]


async def test_list_projetos_ordenado_por_modelo_e_isolado_por_tenant(
    client, session, cenario, token_sistema
):
    """Ordem de id (A1, C1, C8) e de associação (C8, A1, C1) divergem da de
    modelo (C-130, KC-390, zz-1): só `ORDER BY modelo` acerta. O modelo novo
    é minúsculo para ficar depois dos do seed em qualquer collation, qualquer
    que seja a caixa que a migration deu a eles."""
    session.add(ProjetoAnv(id_projeto='A1', modelo='zz-1'))
    await session.flush()
    session.add(TenantProjeto(uae=TEN, projeto='A1'))
    await session.commit()
    add = await client.post(
        f'{URL}{TEN}/projetos',
        json={'projeto': 'C1'},
        headers=bearer(token_sistema),
    )
    assert add.status_code == HTTPStatus.CREATED

    response = await client.get(
        f'{URL}{TEN}/projetos', headers=bearer(token_sistema)
    )
    seed = await client.get(
        f'{URL}1gt/projetos', headers=bearer(token_sistema)
    )

    data = response.json()['data']
    assert [p['id_projeto'] for p in data] == ['C1', 'C8', 'A1']
    assert [p['modelo'].upper() for p in data] == [
        'C-130',
        'KC-390',
        'ZZ-1',
    ]
    # o tenant do seed só enxerga o próprio projeto
    assert seed.json()['data'] == [
        {'id_projeto': 'C1', 'modelo': await modelo_de(session, 'C1')}
    ]


async def test_add_projeto_ok(client, session, cenario, token_sistema):
    response = await client.post(
        f'{URL}{TEN}/projetos',
        json={'projeto': 'C1'},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()
    assert body['message'] == 'Projeto associado com sucesso'
    assert body['data'] == {
        'id_projeto': 'C1',
        'modelo': await modelo_de(session, 'C1'),
    }
    assert await projetos_de(session, TEN) == ['C1', 'C8']
    # não vaza para o tenant do seed
    assert await projetos_de(session, '11gt') == ['C8']


async def test_add_projeto_normaliza_caixa_do_id(
    client, session, token_sistema
):
    """`c8` no corpo vira `C8`; a '1gt' (seed) só operava o C1."""
    response = await client.post(
        f'{URL}1gt/projetos',
        json={'projeto': 'c8'},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()['data']['id_projeto'] == 'C8'
    assert await projetos_de(session, '1gt') == ['C1', 'C8']


async def test_remove_projeto_ok_so_do_tenant_alvo(
    client, session, cenario, token_sistema
):
    response = await client.delete(
        f'{URL}{TEN}/projetos/C8', headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['message'] == 'Projeto desassociado com sucesso'
    assert await projetos_de(session, TEN) == []
    # C8 continua associado à '11gt'
    assert await projetos_de(session, '11gt') == ['C8']


async def test_remove_projeto_acha_id_em_minusculas_na_url(
    client, session, cenario, token_sistema
):
    response = await client.delete(
        f'{URL}{TEN}/projetos/c8', headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.OK
    assert await projetos_de(session, TEN) == []
    assert await projetos_de(session, '11gt') == ['C8']


# ---------------------------------------------------------------- erros


async def test_create_org_inexistente_404(client, session, token_sistema):
    antes = await n_tenants(session)

    response = await client.post(
        URL,
        json={'organizacao_id': 'nao-existe'},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert (
        response.json()['message'] == 'Organização não encontrada no diretório'
    )
    assert await n_tenants(session) == antes


async def test_create_tenant_ja_existente_409(client, session, token_sistema):
    antes = await n_tenants(session)

    response = await client.post(
        URL, json={'organizacao_id': '11gt'}, headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert (
        response.json()['message']
        == 'Organização já é um tenant da plataforma'
    )
    assert await n_tenants(session) == antes


async def test_create_sem_organizacao_id_422(client, token_sistema):
    response = await client.post(URL, json={}, headers=bearer(token_sistema))

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert 'body.organizacao_id' in response.json()['errors']


@pytest.mark.parametrize(
    ('body', 'campo'),
    [
        ({'tema': 'rosa-choque'}, 'body.tema'),
        ({'active': 'talvez'}, 'body.active'),
        ({'saudacao': 's' * 121}, 'body.saudacao'),
    ],
)
async def test_update_payload_invalido_422(
    client, session, cenario, token_sistema, body, campo
):
    response = await client.patch(
        f'{URL}{TEN}', json=body, headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert campo in response.json()['errors']
    tenant = await buscar_tenant(session, TEN)
    assert (tenant.active, tenant.tema, tenant.saudacao) == (True, 'red', '')


async def test_update_inexistente_404(client, token_sistema):
    response = await client.patch(
        f'{URL}nao-existe',
        json={'active': False},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Tenant não encontrado'


async def test_update_de_org_que_nao_e_tenant_404(
    client, cenario, token_sistema
):
    response = await client.patch(
        f'{URL}{ORG}', json={'active': False}, headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Tenant não encontrado'


async def test_delete_inexistente_404(client, token_sistema):
    response = await client.delete(
        f'{URL}nao-existe', headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Tenant não encontrado'


async def test_delete_com_perfis_vinculados_409_e_nada_removido(
    client, session, cenario, users, token_sistema
):
    """FK RESTRICT de `user_roles` antecipada: tenant e projetos ficam."""
    _, other_user = users
    session.add(
        UserRole(
            user_id=other_user.id,
            role_id=await role_existente(session),
            organizacao_id=TEN,
        )
    )
    await session.commit()

    response = await client.delete(
        f'{URL}{TEN}', headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert 'perfis vinculados' in response.json()['message']
    assert await buscar_tenant(session, TEN) is not None
    assert await projetos_de(session, TEN) == ['C8']


async def test_delete_com_dados_vinculados_sem_perfis_409(
    client, session, token_sistema
):
    """A '1gt' (seed) não tem perfil algum, mas `funcoes_uae` a referencia
    por FK: o banco recusa e a rota responde 409 (antes, 500). O rollback da
    rota desfaz o que o teste criou; o tenant do seed sobrevive a ele."""
    perfis = await session.scalar(
        select(func.count())
        .select_from(UserRole)
        .where(UserRole.organizacao_id == '1gt')
    )
    funcoes = await session.scalar(
        select(func.count())
        .select_from(FuncaoUae)
        .where(FuncaoUae.uae == '1gt')
    )
    assert perfis == 0
    assert funcoes > 0

    response = await client.delete(f'{URL}1gt', headers=bearer(token_sistema))

    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()['message'].startswith(
        'Tenant possui dados vinculados'
    )
    assert await buscar_tenant(session, '1gt') is not None
    assert await projetos_de(session, '1gt') == ['C1']


async def test_delete_liberado_quando_perfis_sao_removidos(
    client, session, cenario, users, token_sistema
):
    _, other_user = users
    vinculo = UserRole(
        user_id=other_user.id,
        role_id=await role_existente(session),
        organizacao_id=TEN,
    )
    session.add(vinculo)
    await session.commit()
    bloqueado = await client.delete(
        f'{URL}{TEN}', headers=bearer(token_sistema)
    )
    assert bloqueado.status_code == HTTPStatus.CONFLICT

    await session.delete(vinculo)
    await session.commit()

    liberado = await client.delete(
        f'{URL}{TEN}', headers=bearer(token_sistema)
    )
    assert liberado.status_code == HTTPStatus.OK
    assert await buscar_tenant(session, TEN) is None


async def test_list_projetos_tenant_inexistente_404(client, token_sistema):
    response = await client.get(
        f'{URL}nao-existe/projetos', headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Tenant não encontrado'


async def test_add_projeto_tenant_inexistente_404(client, token_sistema):
    response = await client.post(
        f'{URL}nao-existe/projetos',
        json={'projeto': 'C1'},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Tenant não encontrado'


async def test_add_projeto_inexistente_404_e_nada_associado(
    client, session, cenario, token_sistema
):
    response = await client.post(
        f'{URL}{TEN}/projetos',
        json={'projeto': 'ZZ'},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Projeto não encontrado'
    assert await projetos_de(session, TEN) == ['C8']


async def test_add_projeto_duplicado_409_sem_segunda_linha(
    client, session, cenario, token_sistema
):
    response = await client.post(
        f'{URL}{TEN}/projetos',
        json={'projeto': 'C8'},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert (
        response.json()['message'] == 'Projeto já associado a esta organização'
    )
    assert await projetos_de(session, TEN) == ['C8']


@pytest.mark.parametrize('body', [{}, {'projeto': 'C'}, {'projeto': 'C81'}])
async def test_add_projeto_payload_invalido_422(
    client, session, cenario, token_sistema, body
):
    response = await client.post(
        f'{URL}{TEN}/projetos', json=body, headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert 'body.projeto' in response.json()['errors']
    assert await projetos_de(session, TEN) == ['C8']


async def test_remove_projeto_nao_associado_404(
    client, session, cenario, token_sistema
):
    """C1 existe, mas não está associado a `TEN` (só à '1gt')."""
    response = await client.delete(
        f'{URL}{TEN}/projetos/C1', headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Associação não encontrada'
    assert await projetos_de(session, '1gt') == ['C1']


async def test_remove_projeto_inexistente_404(
    client, session, cenario, token_sistema
):
    response = await client.delete(
        f'{URL}{TEN}/projetos/ZZ', headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Associação não encontrada'
    assert await projetos_de(session, TEN) == ['C8']


async def test_remove_projeto_tenant_inexistente_404(client, token_sistema):
    response = await client.delete(
        f'{URL}nao-existe/projetos/C8', headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Associação não encontrada'
