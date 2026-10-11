"""Router `/organizacoes` (diretório universal de organizações).

Contrato fixado aqui:

- `GET /` e `GET /{sigla}` são abertos a qualquer autenticado (o client usa o
  diretório para siglas/nomes/brasão);
- `POST`, `PUT` e `DELETE` exigem admin de SISTEMA (`require_system_admin`):
  `active_org` nulo + vínculo admin sem organização. Admin de unidade
  (`token`, admin na '11gt') e usuário sem permissão (`token_sem_perm`) levam
  403 `SCOPE_FORBIDDEN`; sem token, 401.

O client de teste compartilha a sessão com o teste: para provar que o banco
NÃO mudou, as leituras usam `populate_existing` e não o identity map.
"""

from http import HTTPStatus

import pytest
from sqlalchemy import func, select

from fcontrol_api.models.shared.organizacao import Organizacao
from fcontrol_api.models.shared.tenant import Tenant
from tests.factories import UserFactory

pytestmark = pytest.mark.anyio

URL = '/organizacoes/'
NOVA = 'zzorg'


def bearer(token):
    return {'Authorization': f'Bearer {token}'}


async def buscar(session, sigla):
    """Relê a linha do banco, ignorando o identity map da sessão."""
    return await session.scalar(
        select(Organizacao)
        .where(Organizacao.sigla == sigla)
        .execution_options(populate_existing=True)
    )


async def buscar_tenant(session, sigla):
    return await session.scalar(
        select(Tenant)
        .where(Tenant.organizacao_id == sigla)
        .execution_options(populate_existing=True)
    )


async def total(session):
    return await session.scalar(select(func.count(Organizacao.sigla)))


@pytest.fixture
async def org_nova(session):
    org = Organizacao(
        sigla=NOVA,
        nome='Organizacao Nova',
        alias='nova',
        sigla_2='zzorg2',
        sigla_3='zzorg3',
    )
    session.add(org)
    await session.commit()
    return org


# ---------------------------------------------------------------- gate


# (método, url, corpo) — cada rota de escrita, alvo existente (`org_nova`)
ESCRITAS = [
    ('POST', URL, {'sigla': 'zzpost', 'nome': 'Nao deve existir'}),
    ('PUT', f'{URL}{NOVA}', {'nome': 'Nome Alterado'}),
    ('DELETE', f'{URL}{NOVA}', None),
]


async def _assert_barrada(client, session, tk, method, url, body):
    antes = await total(session)

    response = await client.request(method, url, json=body, headers=bearer(tk))

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json()['message'] == 'SCOPE_FORBIDDEN'

    assert await total(session) == antes
    assert await buscar(session, 'zzpost') is None
    org = await buscar(session, NOVA)
    assert org is not None
    assert org.nome == 'Organizacao Nova'


@pytest.mark.parametrize(('method', 'url', 'body'), ESCRITAS)
async def test_escrita_barrada_para_admin_de_unidade(
    client, session, org_nova, token, method, url, body
):
    """Admin da '11gt' não administra o sistema: 403 e banco intacto."""
    await _assert_barrada(client, session, token, method, url, body)


@pytest.mark.parametrize(('method', 'url', 'body'), ESCRITAS)
async def test_escrita_barrada_sem_permissao(
    client, session, org_nova, token_sem_perm, method, url, body
):
    await _assert_barrada(client, session, token_sem_perm, method, url, body)


@pytest.mark.parametrize(('method', 'url', 'body'), ESCRITAS)
async def test_escrita_sem_token_401(client, method, url, body):
    response = await client.request(method, url, json=body)

    assert response.status_code == HTTPStatus.UNAUTHORIZED


# --------------------------------------------------------- leitura aberta


async def test_list_aberta_a_autenticado_sem_permissao(client, token_sem_perm):
    """Contrato atual: sem gate — qualquer autenticado lista o diretório."""
    response = await client.get(URL, headers=bearer(token_sem_perm))

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    siglas = [o['sigla'] for o in data]
    assert {'11gt', '1gt'} <= set(siglas)
    assert set(data[0]) == {
        'sigla',
        'nome',
        'sigla_2',
        'sigla_3',
        'alias',
        'created_at',
    }


async def test_list_ordenada_por_sigla(client, session, token_sem_perm):
    """A ordem de inserção contradiz a de sigla: 'zzord' entra antes de
    '0zz', e ambos depois do seed, então só `ORDER BY sigla` acerta."""
    session.add(Organizacao(sigla='zzord', nome='Ultima'))
    await session.flush()
    session.add(Organizacao(sigla='0zz', nome='Primeira'))
    await session.commit()

    response = await client.get(URL, headers=bearer(token_sem_perm))

    siglas = [o['sigla'] for o in response.json()['data']]
    assert [s for s in siglas if s in {'0zz', '11gt', '1gt', 'zzord'}] == [
        '0zz',
        '11gt',
        '1gt',
        'zzord',
    ]
    assert siglas == sorted(siglas)


async def test_get_aberta_a_autenticado_sem_permissao(client, token_sem_perm):
    response = await client.get(f'{URL}11gt', headers=bearer(token_sem_perm))

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert data['sigla'] == '11gt'
    assert data['nome'] == 'Primeiro Esquadrão do Primeiro GT'


async def test_get_inexistente_404(client, token_sem_perm):
    response = await client.get(
        f'{URL}nao-existe', headers=bearer(token_sem_perm)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Organização não encontrada'


@pytest.mark.parametrize('url', [URL, f'{URL}11gt'])
async def test_leitura_sem_token_401(client, url):
    response = await client.get(url)

    assert response.status_code == HTTPStatus.UNAUTHORIZED


# ------------------------------------------------------------- CRUD feliz


async def test_create_ok(client, session, token_sistema):
    response = await client.post(
        URL,
        json={
            'sigla': NOVA,
            'nome': 'Organizacao Nova',
            'sigla_2': 'zzorg2',
            'sigla_3': 'zzorg3',
            'alias': 'nova',
        },
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()
    assert body['message'] == 'Organização cadastrada com sucesso'
    assert body['data']['sigla'] == NOVA
    assert body['data']['sigla_2'] == 'zzorg2'
    assert body['data']['sigla_3'] == 'zzorg3'
    assert body['data']['alias'] == 'nova'

    org = await buscar(session, NOVA)
    assert org is not None
    assert org.nome == 'Organizacao Nova'


async def test_create_somente_campos_obrigatorios(
    client, session, token_sistema
):
    response = await client.post(
        URL,
        json={'sigla': NOVA, 'nome': 'Organizacao Nova'},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.CREATED
    data = response.json()['data']
    assert data['sigla_2'] is None
    assert data['sigla_3'] is None
    assert data['alias'] is None


async def test_create_apara_espacos_de_sigla_e_nome(
    client, session, token_sistema
):
    response = await client.post(
        URL,
        json={'sigla': f'  {NOVA} ', 'nome': '  Organizacao Nova  '},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()['data']['sigla'] == NOVA
    assert response.json()['data']['nome'] == 'Organizacao Nova'
    org = await buscar(session, NOVA)
    assert org.nome == 'Organizacao Nova'
    assert await buscar(session, f'  {NOVA} ') is None


async def test_org_existente_aparece_na_listagem_e_no_get(
    client, org_nova, token_sem_perm
):
    lista = await client.get(URL, headers=bearer(token_sem_perm))
    one = await client.get(f'{URL}{NOVA}', headers=bearer(token_sem_perm))

    assert NOVA in [o['sigla'] for o in lista.json()['data']]
    assert one.status_code == HTTPStatus.OK
    assert one.json()['data']['nome'] == 'Organizacao Nova'


async def test_update_parcial_preserva_demais_campos(
    client, session, org_nova, token_sistema
):
    response = await client.put(
        f'{URL}{NOVA}',
        json={'nome': 'Nome Alterado'},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body['message'] == 'Organização atualizada com sucesso'
    assert body['data']['nome'] == 'Nome Alterado'
    assert body['data']['alias'] == 'nova'

    org = await buscar(session, NOVA)
    assert org.nome == 'Nome Alterado'
    assert org.alias == 'nova'


@pytest.mark.parametrize('campo', ['alias', 'sigla_2', 'sigla_3'])
async def test_update_campo_opcional_explicitamente_nulo_limpa(
    client, session, org_nova, token_sistema, campo
):
    """`exclude_unset`: campo nullable enviado como null é limpo (só
    `sigla` e `nome` recusam null) e os demais ficam como estavam."""
    antes = {c: getattr(org_nova, c) for c in ('alias', 'sigla_2', 'sigla_3')}
    assert all(antes.values())

    response = await client.put(
        f'{URL}{NOVA}', json={campo: None}, headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.OK
    org = await buscar(session, NOVA)
    for c, valor in antes.items():
        assert getattr(org, c) == (None if c == campo else valor)


async def test_update_apara_espacos_de_nome(
    client, session, org_nova, token_sistema
):
    response = await client.put(
        f'{URL}{NOVA}',
        json={'nome': '  Nome Alterado  '},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.OK
    assert (await buscar(session, NOVA)).nome == 'Nome Alterado'


async def test_update_pode_renomear_sigla(
    client, session, org_nova, token_sistema
):
    response = await client.put(
        f'{URL}{NOVA}',
        json={'sigla': 'zzrenom'},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['data']['sigla'] == 'zzrenom'
    assert await buscar(session, NOVA) is None
    assert await buscar(session, 'zzrenom') is not None


async def test_update_sigla_de_tenant_409_e_nada_renomeado(
    client, session, org_nova, token_sistema
):
    """A sigla de um tenant não muda (user_roles a referencia sem cascade).
    O 409 é antecipado, sem rollback: a linha criada no teste sobrevive e
    prova que nem a sigla nem o nome foram tocados."""
    session.add(Tenant(organizacao_id=NOVA))
    await session.commit()

    response = await client.put(
        f'{URL}{NOVA}',
        json={'sigla': 'zzrenom', 'nome': 'Nome Alterado'},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert (
        response.json()['message']
        == 'A sigla de um tenant da plataforma não pode ser alterada.'
    )
    assert await buscar(session, 'zzrenom') is None
    org = await buscar(session, NOVA)
    assert org.nome == 'Organizacao Nova'
    assert await buscar_tenant(session, NOVA) is not None


async def test_update_de_tenant_com_a_mesma_sigla_200(
    client, session, org_nova, token_sistema
):
    """Reenviar a sigla atual (o formulário manda o objeto inteiro) não é
    renomear: o bloqueio de tenant não se aplica."""
    session.add(Tenant(organizacao_id=NOVA))
    await session.commit()

    response = await client.put(
        f'{URL}{NOVA}',
        json={'sigla': NOVA, 'nome': 'Nome Alterado'},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['data']['sigla'] == NOVA
    assert (await buscar(session, NOVA)).nome == 'Nome Alterado'


async def test_delete_ok(client, session, org_nova, token_sistema):
    response = await client.delete(
        f'{URL}{NOVA}', headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['message'] == 'Organização removida com sucesso'
    assert await buscar(session, NOVA) is None


# ---------------------------------------------------------------- erros


async def test_update_inexistente_404(client, token_sistema):
    response = await client.put(
        f'{URL}nao-existe',
        json={'nome': 'X'},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Organização não encontrada'


async def test_delete_inexistente_404(client, token_sistema):
    response = await client.delete(
        f'{URL}nao-existe', headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Organização não encontrada'


async def test_delete_org_com_usuario_409(
    client, session, org_nova, token_sistema
):
    """Org que não é tenant mas tem usuário (`users.unidade`, FK RESTRICT):
    409, não 500. O rollback da rota desfaz também a org criada aqui, então
    a prova é o status e a mensagem."""
    session.add(UserFactory(unidade=NOVA))
    await session.commit()

    response = await client.delete(
        f'{URL}{NOVA}', headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()['message'].startswith(
        'Organização em uso por usuários ou outros registros.'
    )


async def test_create_sigla_duplicada_409(client, session, token_sistema):
    """'11gt' já existe no seed: 409 e a linha original não é tocada."""
    response = await client.post(
        URL,
        json={'sigla': '11gt', 'nome': 'Impostora'},
        headers=bearer(token_sistema),
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert (
        response.json()['message']
        == 'Já existe uma organização com uma dessas siglas'
    )
    org = await buscar(session, '11gt')
    assert org.nome == 'Primeiro Esquadrão do Primeiro GT'


async def test_create_sigla_2_duplicada_409(client, token_sistema):
    primeira = await client.post(
        URL,
        json={'sigla': NOVA, 'nome': 'Primeira', 'sigla_2': 'zzdup'},
        headers=bearer(token_sistema),
    )
    assert primeira.status_code == HTTPStatus.CREATED

    segunda = await client.post(
        URL,
        json={'sigla': 'zzorg-b', 'nome': 'Segunda', 'sigla_2': 'zzdup'},
        headers=bearer(token_sistema),
    )

    assert segunda.status_code == HTTPStatus.CONFLICT
    assert (
        segunda.json()['message']
        == 'Já existe uma organização com uma dessas siglas'
    )
    # O rollback da rota desfaz a transação inteira do teste, inclusive a
    # `primeira`: ela não é relida aqui porque o resultado seria vazio por
    # construção, não por a rota ter preservado alguma coisa.


async def test_update_sigla_2_duplicada_409(client, token_sistema):
    for sigla, sigla_2 in (('zza', 'zzs2a'), ('zzb', 'zzs2b')):
        r = await client.post(
            URL,
            json={'sigla': sigla, 'nome': sigla, 'sigla_2': sigla_2},
            headers=bearer(token_sistema),
        )
        assert r.status_code == HTTPStatus.CREATED

    response = await client.put(
        f'{URL}zzb', json={'sigla_2': 'zzs2a'}, headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert (
        response.json()['message']
        == 'Já existe uma organização com uma dessas siglas'
    )


async def test_update_sigla_para_existente_409(
    client, session, org_nova, token_sistema
):
    """Renomear a sigla (PK) de uma org que não é tenant para uma que já
    existe é conflito. A '11gt' (seed) segue intacta após o rollback."""
    response = await client.put(
        f'{URL}{NOVA}', json={'sigla': '11gt'}, headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert (
        response.json()['message']
        == 'Já existe uma organização com uma dessas siglas'
    )
    org = await buscar(session, '11gt')
    assert org.nome == 'Primeiro Esquadrão do Primeiro GT'


async def test_delete_de_tenant_409_e_nada_removido(
    client, session, token_sistema
):
    """Org que é tenant não sai do diretório (FK RESTRICT antecipada)."""
    response = await client.delete(f'{URL}11gt', headers=bearer(token_sistema))

    assert response.status_code == HTTPStatus.CONFLICT
    assert 'é um tenant da plataforma' in response.json()['message']
    assert await buscar(session, '11gt') is not None
    assert await buscar_tenant(session, '11gt') is not None


async def test_delete_org_deixa_de_ser_tenant_so_apos_descadastrar(
    client, session, org_nova, token_sistema
):
    """O 409 some quando o tenant é removido: a checagem é de dependência."""
    session.add(Tenant(organizacao_id=NOVA))
    await session.commit()

    bloqueado = await client.delete(
        f'{URL}{NOVA}', headers=bearer(token_sistema)
    )
    assert bloqueado.status_code == HTTPStatus.CONFLICT
    assert await buscar(session, NOVA) is not None

    await session.delete(await session.get(Tenant, NOVA))
    await session.commit()

    liberado = await client.delete(
        f'{URL}{NOVA}', headers=bearer(token_sistema)
    )
    assert liberado.status_code == HTTPStatus.OK
    assert await buscar(session, NOVA) is None


@pytest.mark.parametrize(
    ('body', 'campo'),
    [
        ({'nome': 'Sem sigla'}, 'body.sigla'),
        ({'sigla': 'zzx'}, 'body.nome'),
        ({'sigla': '', 'nome': 'Sigla vazia'}, 'body.sigla'),
        ({'sigla': '   ', 'nome': 'Sigla em branco'}, 'body.sigla'),
        ({'sigla': 'zzx', 'nome': ''}, 'body.nome'),
        ({'sigla': 'zzx', 'nome': '   '}, 'body.nome'),
        ({'sigla': None, 'nome': 'Sigla nula'}, 'body.sigla'),
        ({'sigla': 'zzx', 'nome': None}, 'body.nome'),
        ({'sigla': 'x' * 21, 'nome': 'Sigla longa'}, 'body.sigla'),
        ({'sigla': 'zzx', 'nome': 'n' * 151}, 'body.nome'),
        ({'sigla': 'zzx', 'nome': 'ok', 'sigla_2': 'x' * 21}, 'body.sigla_2'),
        ({'sigla': 'zzx', 'nome': 'ok', 'alias': 'a' * 101}, 'body.alias'),
    ],
)
async def test_create_payload_invalido_422(
    client, session, token_sistema, body, campo
):
    antes = await total(session)

    response = await client.post(URL, json=body, headers=bearer(token_sistema))

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert campo in response.json()['errors']
    assert await total(session) == antes


@pytest.mark.parametrize(
    ('body', 'campo'),
    [
        ({'nome': 'n' * 151}, 'body.nome'),
        ({'sigla': 'x' * 21}, 'body.sigla'),
        ({'sigla': None}, 'body.sigla'),
        ({'nome': None}, 'body.nome'),
        ({'sigla': '', 'nome': 'Ok'}, 'body.sigla'),
        ({'sigla': '   '}, 'body.sigla'),
        ({'nome': ''}, 'body.nome'),
        ({'nome': '   '}, 'body.nome'),
    ],
)
async def test_update_payload_invalido_422(
    client, session, org_nova, token_sistema, body, campo
):
    """`sigla`/`nome` podem faltar, mas não ser null nem vazios: o null
    virava IntegrityError e saía como 409 de sigla duplicada."""
    response = await client.put(
        f'{URL}{NOVA}', json=body, headers=bearer(token_sistema)
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert campo in response.json()['errors']
    org = await buscar(session, NOVA)
    assert org is not None
    assert org.nome == 'Organizacao Nova'
