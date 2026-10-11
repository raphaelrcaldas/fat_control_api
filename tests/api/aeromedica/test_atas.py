"""Atas de inspeção de saúde (/aeromedica/atas).

Atas penduram num User (diretório global) escopado por `User.unidade`: a org
ativa é a lente de upload, listagem, edição e remoção. Compartilham o recurso
RBAC `aeromedica.cartoes` e, ao subir/editar, empurram o CEMAL do cartão do
militar (só para frente — ver `_upsert_cemal`).

Storage, compressão e extração do PDF são trocados por fakes no namespace do
router: o teste não depende de MinIO, de `gs` nem de PDF real.
"""

import json
from datetime import UTC, date, datetime
from http import HTTPStatus

import pytest
from sqlalchemy import func, select

from fcontrol_api.models.aeromedica.atas import AtaInspecao
from fcontrol_api.models.aeromedica.cartoes import CartaoSaude
from fcontrol_api.models.security.logs import UserActionLog
from fcontrol_api.models.security.resources import (
    Permissions,
    Resources,
    RolePermissions,
    Roles,
    UserRole,
)
from fcontrol_api.routers.aeromedica import atas
from tests.factories import UserFactory

pytestmark = pytest.mark.anyio

URL = '/aeromedica/atas/'
LOG_RESOURCE = 'aeromedica.cartoes'  # também o recurso RBAC
PREFIXO = 'atas-inspecao'

REALIZACAO = date(2026, 3, 10)
VALIDADE = date(2027, 3, 10)


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def _pdf(conteudo: bytes = b'ata') -> bytes:
    return b'%PDF-1.4\n%' + conteudo + b'\n%%EOF\n'


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def storage(monkeypatch):
    """Bucket em memória + compressão neutra."""
    objetos: dict[str, bytes] = {}

    def fake_upload(bucket, path, data, content_type, size):
        objetos[path] = data

    def fake_delete(bucket, path):
        objetos.pop(path, None)

    def fake_url(bucket, path, expires=900, content_disposition=None):
        return f'https://storage.test/{bucket}/{path}'

    monkeypatch.setattr(atas, 'upload_file', fake_upload)
    monkeypatch.setattr(atas, 'delete_file', fake_delete)
    monkeypatch.setattr(atas, 'get_signed_url', fake_url)
    monkeypatch.setattr(atas, 'comprimir_pdf', lambda c: c + b'#z')
    return objetos


@pytest.fixture
def extracao(monkeypatch):
    """Resultado da extração do PDF (mutável) e contagem de chamadas."""
    dados = {
        'nome_completo': None,
        'letra_finalidade': 'A',
        'data_realizacao': REALIZACAO,
        'validade_inspsau': VALIDADE,
    }
    chamadas: list[int] = []

    def fake_extrair(conteudo):
        chamadas.append(len(conteudo))
        return dict(dados)

    monkeypatch.setattr(atas, 'extrair_dados_ata_bytes', fake_extrair)
    dados['_chamadas'] = chamadas
    return dados


@pytest.fixture
async def militar(session):
    """Militar da org '11gt' (a lente do token padrão)."""
    user = UserFactory(unidade='11gt', nome_guerra='Zé Ação')
    user.nome_completo = 'José Ação da Silva'
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.fixture
async def militar_1gt(session):
    """Militar da org '1gt' (fora da lente do token padrão)."""
    user = UserFactory(unidade='1gt')
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.fixture
async def admin_1gt_token(users, session, make_org_token):
    """Token com org ativa '1gt' e vínculo admin nessa org."""
    _, other = users
    session.add(UserRole(user_id=other.id, role_id=1, organizacao_id='1gt'))
    await session.commit()
    return await make_org_token(other, active_org='1gt')


@pytest.fixture
async def viewer_token(users, session, make_org_token):
    """Role não-admin na '11gt' com SÓ `aeromedica.cartoes.view`."""
    _, other = users
    res = await session.scalar(
        select(Resources).where(Resources.name == LOG_RESOURCE)
    )
    if res is None:
        res = Resources(name=LOG_RESOURCE, description=LOG_RESOURCE)
        session.add(res)
        await session.flush()
    perm = await session.scalar(
        select(Permissions).where(
            Permissions.resource_id == res.id, Permissions.name == 'view'
        )
    )
    if perm is None:
        perm = Permissions(resource_id=res.id, name='view', description='v')
        session.add(perm)
        await session.flush()
    role = Roles(name='cartoes_viewer', description='cartoes_viewer')
    session.add(role)
    await session.flush()
    session.add(RolePermissions(role_id=role.id, permission_id=perm.id))
    session.add(
        UserRole(user_id=other.id, role_id=role.id, organizacao_id='11gt')
    )
    await session.commit()
    return await make_org_token(other)


# ── Helpers ───────────────────────────────────────────────────────


async def _enviar(
    client,
    token,
    user_id,
    *,
    nome='ata.pdf',
    conteudo=None,
    **params,
):
    return await client.post(
        URL,
        params={'user_id': user_id, **params},
        files={
            'file': (
                nome,
                _pdf() if conteudo is None else conteudo,
                'application/pdf',
            )
        },
        headers=_auth(token),
    )


async def _mk_ata(session, storage, user_id, **kw):
    """Insere uma ata direto no banco, com o objeto no storage fake."""
    created_at = kw.pop('created_at', None)
    campos = {
        'letra_finalidade': 'A',
        'data_realizacao': REALIZACAO,
        'validade_inspsau': VALIDADE,
    } | kw
    path = f'{PREFIXO}/{user_id}/{len(storage)}_x.pdf'
    storage[path] = b'%PDF-conteudo'
    ata = AtaInspecao(
        user_id=user_id,
        file_path=path,
        file_name='x.pdf',
        file_size=13,
        **campos,
    )
    if created_at is not None:
        ata.created_at = created_at
    session.add(ata)
    await session.commit()
    await session.refresh(ata)
    return ata


async def _mk_cartao(session, user_id, cemal):
    cartao = CartaoSaude(user_id=user_id, cemal=cemal, tovn=None, imae=None)
    session.add(cartao)
    await session.commit()
    return cartao


async def _atas(session, user_id):
    res = await session.execute(
        select(AtaInspecao)
        .where(AtaInspecao.user_id == user_id)
        .order_by(AtaInspecao.id)
        .execution_options(populate_existing=True)
    )
    return res.scalars().all()


async def _cartao(session, user_id):
    return await session.scalar(
        select(CartaoSaude)
        .where(CartaoSaude.user_id == user_id)
        .execution_options(populate_existing=True)
    )


async def _logs(session, action):
    res = await session.execute(
        select(UserActionLog).where(
            UserActionLog.resource == LOG_RESOURCE,
            UserActionLog.action == action,
        )
    )
    return res.scalars().all()


async def _total_atas(session):
    return await session.scalar(select(func.count(AtaInspecao.id)))


# ── Isolamento por org ────────────────────────────────────────────


async def test_upload_militar_de_outra_org_404_sem_efeitos(
    client, session, token, militar_1gt, storage, extracao
):
    resp = await _enviar(client, token, militar_1gt.id)

    assert resp.status_code == HTTPStatus.NOT_FOUND
    assert storage == {}
    assert await _total_atas(session) == 0
    assert await _cartao(session, militar_1gt.id) is None
    assert await _logs(session, 'ata_create') == []


async def test_upload_militar_inexistente_404(
    client, token, storage, extracao
):
    resp = await _enviar(client, token, 999999)

    assert resp.status_code == HTTPStatus.NOT_FOUND
    assert storage == {}


async def test_extrair_militar_de_outra_org_404(
    client, token, militar_1gt, storage, extracao
):
    resp = await client.post(
        f'{URL}extrair',
        params={'user_id': militar_1gt.id},
        files={'file': ('ata.pdf', _pdf(), 'application/pdf')},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.NOT_FOUND
    assert extracao['_chamadas'] == []


async def test_get_nao_lista_ata_de_outra_org(
    client, session, token, admin_1gt_token, militar_1gt, storage
):
    ata = await _mk_ata(session, storage, militar_1gt.id)

    de_fora = await client.get(
        f'{URL}user/{militar_1gt.id}', headers=_auth(token)
    )
    dono = await client.get(
        f'{URL}user/{militar_1gt.id}', headers=_auth(admin_1gt_token)
    )

    assert de_fora.status_code == HTTPStatus.OK
    assert de_fora.json()['data'] == []
    assert [a['id'] for a in dono.json()['data']] == [ata.id]


async def test_patch_ata_de_outra_org_404_sem_alterar(
    client, session, token, militar_1gt, storage
):
    ata = await _mk_ata(session, storage, militar_1gt.id)

    resp = await client.patch(
        f'{URL}{ata.id}',
        json={'letra_finalidade': 'B', 'validade_inspsau': '2030-01-01'},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.NOT_FOUND
    assert resp.json()['message'] == 'Ata não encontrada'
    [depois] = await _atas(session, militar_1gt.id)
    assert depois.letra_finalidade == 'A'
    assert depois.validade_inspsau == VALIDADE
    assert await _cartao(session, militar_1gt.id) is None
    assert await _logs(session, 'ata_update') == []


async def test_delete_ata_de_outra_org_404_sem_remover(
    client, session, token, militar_1gt, storage
):
    ata = await _mk_ata(session, storage, militar_1gt.id)

    resp = await client.delete(f'{URL}{ata.id}', headers=_auth(token))

    assert resp.status_code == HTTPStatus.NOT_FOUND
    assert resp.json()['message'] == 'Ata não encontrada'
    assert len(await _atas(session, militar_1gt.id)) == 1
    assert ata.file_path in storage
    assert await _logs(session, 'ata_delete') == []


# ── Gate ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ('metodo', 'sufixo'),
    [
        ('post', ''),
        ('post', 'extrair'),
        ('get', 'user/{uid}'),
        ('patch', '{aid}'),
        ('delete', '{aid}'),
    ],
)
async def test_sem_permissao_403_sem_efeitos(
    client,
    session,
    token_sem_perm,
    militar,
    storage,
    extracao,
    metodo,
    sufixo,
):
    ata = await _mk_ata(session, storage, militar.id)
    kwargs = {'headers': _auth(token_sem_perm)}
    if metodo == 'post':
        kwargs['params'] = {'user_id': militar.id}
        kwargs['files'] = {'file': ('ata.pdf', _pdf(), 'application/pdf')}
    elif metodo == 'patch':
        kwargs['json'] = {'letra_finalidade': 'B'}

    resp = await client.request(
        metodo.upper(),
        URL + sufixo.format(uid=militar.id, aid=ata.id),
        **kwargs,
    )

    assert resp.status_code == HTTPStatus.FORBIDDEN
    [depois] = await _atas(session, militar.id)
    assert depois.id == ata.id
    assert depois.letra_finalidade == 'A'
    assert list(storage) == [ata.file_path]
    assert extracao['_chamadas'] == []


async def test_view_nao_basta_para_escrever(
    client, session, viewer_token, militar, storage, extracao
):
    ata = await _mk_ata(session, storage, militar.id)

    leitura = await client.get(
        f'{URL}user/{militar.id}', headers=_auth(viewer_token)
    )
    upload = await _enviar(client, viewer_token, militar.id)
    patch = await client.patch(
        f'{URL}{ata.id}',
        json={'letra_finalidade': 'B'},
        headers=_auth(viewer_token),
    )
    delete = await client.delete(f'{URL}{ata.id}', headers=_auth(viewer_token))

    assert leitura.status_code == HTTPStatus.OK
    assert upload.status_code == HTTPStatus.FORBIDDEN
    assert patch.status_code == HTTPStatus.FORBIDDEN
    assert delete.status_code == HTTPStatus.FORBIDDEN
    assert len(await _atas(session, militar.id)) == 1
    assert list(storage) == [ata.file_path]


async def test_sem_token_401(client):
    resp = await client.get(f'{URL}user/1')
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


# ── Upload ────────────────────────────────────────────────────────


async def test_upload_feliz_grava_ata_storage_cartao_e_log(
    client, session, token, users, militar, storage, extracao
):
    user, _ = users
    pdf = _pdf(b'conteudo-unico')

    resp = await _enviar(client, token, militar.id, conteudo=pdf)

    assert resp.status_code == HTTPStatus.CREATED
    corpo = resp.json()
    assert corpo['message'] == 'Ata enviada com sucesso'
    assert corpo['data']['cemal_atualizado'] is True
    assert corpo['data']['extracao_vazia'] is False
    assert corpo['data']['dados_extraidos']['letra_finalidade'] == 'A'

    [ata] = await _atas(session, militar.id)
    assert ata.letra_finalidade == 'A'
    assert ata.data_realizacao == REALIZACAO
    assert ata.validade_inspsau == VALIDADE
    assert ata.file_name == 'ze_acao_2026-03-10.pdf'
    # o router grava o tamanho do arquivo já comprimido (fake: +2 bytes)
    assert ata.file_size == len(pdf) + 2
    assert ata.file_path.startswith(f'{PREFIXO}/{militar.id}/')
    assert ata.file_path.endswith('_ze_acao_2026-03-10.pdf')
    assert storage == {ata.file_path: pdf + b'#z'}
    assert corpo['data']['ata']['id'] == ata.id

    cartao = await _cartao(session, militar.id)
    assert cartao.cemal == VALIDADE
    assert cartao.tovn is None
    assert cartao.imae is None

    [log] = await _logs(session, 'ata_create')
    assert log.user_id == user.id
    assert log.resource_id == militar.id
    after = json.loads(log.after)
    assert after['file_name'] == ata.file_name
    assert after['cemal'] == VALIDADE.isoformat()
    assert after['cartao_criado'] is True


async def test_upload_cemal_avanca_quando_validade_maior(
    client, session, token, militar, storage, extracao
):
    await _mk_cartao(session, militar.id, date(2026, 1, 1))

    resp = await _enviar(client, token, militar.id)

    assert resp.status_code == HTTPStatus.CREATED
    assert resp.json()['data']['cemal_atualizado'] is True
    assert (await _cartao(session, militar.id)).cemal == VALIDADE
    [log] = await _logs(session, 'ata_create')
    after = json.loads(log.after)
    assert after['cemal'] == VALIDADE.isoformat()
    assert 'cartao_criado' not in after


async def test_upload_cemal_preenche_quando_nulo(
    client, session, token, militar, storage, extracao
):
    await _mk_cartao(session, militar.id, None)

    resp = await _enviar(client, token, militar.id)

    assert resp.json()['data']['cemal_atualizado'] is True
    assert (await _cartao(session, militar.id)).cemal == VALIDADE


@pytest.mark.parametrize('cemal', [VALIDADE, date(2030, 1, 1)])
async def test_upload_cemal_nao_regride_nem_repete(
    client, session, token, militar, storage, extracao, cemal
):
    """Validade igual ou menor que o CEMAL atual não mexe no cartão."""
    await _mk_cartao(session, militar.id, cemal)

    resp = await _enviar(client, token, militar.id)

    assert resp.status_code == HTTPStatus.CREATED
    assert resp.json()['data']['cemal_atualizado'] is False
    assert len(await _atas(session, militar.id)) == 1
    assert (await _cartao(session, militar.id)).cemal == cemal
    [log] = await _logs(session, 'ata_create')
    assert 'cemal' not in json.loads(log.after)


async def test_upload_sem_validade_nao_cria_cartao(
    client, session, token, militar, storage, extracao
):
    extracao['validade_inspsau'] = None

    resp = await _enviar(client, token, militar.id)

    assert resp.status_code == HTTPStatus.CREATED
    assert resp.json()['data']['cemal_atualizado'] is False
    assert await _cartao(session, militar.id) is None
    assert len(await _atas(session, militar.id)) == 1


async def test_upload_dados_confirmados_ignora_extracao(
    client, session, token, militar, storage, extracao
):
    resp = await _enviar(
        client,
        token,
        militar.id,
        dados_confirmados=True,
        conf_letra='C',
        conf_realizacao='2026-05-01',
        conf_validade='2028-05-01',
    )

    assert resp.status_code == HTTPStatus.CREATED
    assert extracao['_chamadas'] == []
    [ata] = await _atas(session, militar.id)
    assert ata.letra_finalidade == 'C'
    assert ata.data_realizacao == date(2026, 5, 1)
    assert ata.validade_inspsau == date(2028, 5, 1)
    assert ata.file_name == 'ze_acao_2026-05-01.pdf'
    assert (await _cartao(session, militar.id)).cemal == date(2028, 5, 1)


async def test_upload_conf_letra_com_mais_de_um_caractere_422(
    client, token, militar, storage, extracao
):
    resp = await _enviar(
        client,
        token,
        militar.id,
        dados_confirmados=True,
        conf_letra='AB',
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert storage == {}


async def test_upload_extracao_vazia_aceita_sem_checar_duplicata(
    client, session, token, militar, storage, extracao
):
    extracao.update(
        letra_finalidade=None, data_realizacao=None, validade_inspsau=None
    )

    primeira = await _enviar(client, token, militar.id)
    segunda = await _enviar(client, token, militar.id)

    assert primeira.status_code == HTTPStatus.CREATED
    assert segunda.status_code == HTTPStatus.CREATED
    corpo = primeira.json()
    assert corpo['data']['extracao_vazia'] is True
    assert corpo['message'] == 'Ata enviada. Preencha os dados manualmente.'
    assert corpo['data']['cemal_atualizado'] is False
    assert len(await _atas(session, militar.id)) == 2
    assert await _cartao(session, militar.id) is None


# ── Validação do arquivo e duplicata ──────────────────────────────


async def test_upload_extensao_nao_pdf_400(
    client, session, token, militar, storage, extracao
):
    resp = await _enviar(client, token, militar.id, nome='ata.png')

    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert storage == {}
    assert await _total_atas(session) == 0


async def test_upload_sem_assinatura_pdf_400(
    client, session, token, militar, storage, extracao
):
    resp = await _enviar(
        client, token, militar.id, conteudo=b'nao sou um pdf de verdade'
    )

    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert storage == {}
    assert await _total_atas(session) == 0


async def test_upload_acima_de_10mb_400(
    client, session, token, militar, storage, extracao
):
    grande = b'%PDF-1.4\n' + b'0' * atas.MAX_FILE_SIZE

    resp = await _enviar(client, token, militar.id, conteudo=grande)

    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert resp.json()['message'] == 'Arquivo excede o limite de 10 MB'
    assert storage == {}
    assert await _total_atas(session) == 0


async def test_upload_extensao_maiuscula_aceita(
    client, token, militar, storage, extracao
):
    resp = await _enviar(client, token, militar.id, nome='ATA.PDF')

    assert resp.status_code == HTTPStatus.CREATED


async def test_upload_duplicata_409_sem_segundo_objeto(
    client, session, token, militar, storage, extracao
):
    primeira = await _enviar(client, token, militar.id)
    segunda = await _enviar(client, token, militar.id)

    assert primeira.status_code == HTTPStatus.CREATED
    assert segunda.status_code == HTTPStatus.CONFLICT
    assert len(await _atas(session, militar.id)) == 1
    assert len(storage) == 1
    assert len(await _logs(session, 'ata_create')) == 1


async def test_upload_mesma_ata_para_outro_militar_nao_e_duplicata(
    client, session, token, militar, storage, extracao
):
    outro = UserFactory(unidade='11gt')
    session.add(outro)
    await session.commit()
    await session.refresh(outro)

    primeira = await _enviar(client, token, militar.id)
    segunda = await _enviar(client, token, outro.id)

    assert primeira.status_code == HTTPStatus.CREATED
    assert segunda.status_code == HTTPStatus.CREATED


async def test_upload_validade_diferente_nao_e_duplicata(
    client, token, militar, storage, extracao
):
    await _enviar(client, token, militar.id)
    extracao['validade_inspsau'] = date(2028, 3, 10)

    resp = await _enviar(client, token, militar.id)

    assert resp.status_code == HTTPStatus.CREATED


async def test_upload_falha_ao_gravar_remove_objeto_do_storage(
    client, session, token, militar, storage, extracao, monkeypatch
):
    async def explode(*args, **kwargs):
        raise RuntimeError('banco fora')

    monkeypatch.setattr(atas, '_upsert_cemal', explode)

    with pytest.raises(RuntimeError, match='banco fora'):
        await _enviar(client, token, militar.id)
    await session.rollback()

    # Só `storage == {}` prova algo: o rollback desfaz a transação externa
    # da fixture inteira, então contar atas no banco seria sempre 0.
    assert storage == {}


# ── Extrair ───────────────────────────────────────────────────────


async def _extrair(client, token, user_id, nome='ata.pdf'):
    return await client.post(
        f'{URL}extrair',
        params={'user_id': user_id},
        files={'file': (nome, _pdf(), 'application/pdf')},
        headers=_auth(token),
    )


async def test_extrair_devolve_dados_sem_gravar(
    client, session, token, militar, storage, extracao
):
    extracao['nome_completo'] = 'josé ação da silva '

    resp = await _extrair(client, token, militar.id)

    assert resp.status_code == HTTPStatus.OK
    corpo = resp.json()
    assert corpo['status'] == 'success'
    assert corpo['data']['extracao_vazia'] is False
    assert corpo['data']['dados_extraidos'] == {
        'nome_completo': 'josé ação da silva ',
        'letra_finalidade': 'A',
        'data_realizacao': REALIZACAO.isoformat(),
        'validade_inspsau': VALIDADE.isoformat(),
    }
    assert storage == {}
    assert await _total_atas(session) == 0
    assert await _cartao(session, militar.id) is None
    assert await _logs(session, 'ata_create') == []


async def test_extrair_nome_divergente_vira_aviso(
    client, token, militar, storage, extracao
):
    extracao['nome_completo'] = 'Outra Pessoa'

    resp = await _extrair(client, token, militar.id)

    assert resp.status_code == HTTPStatus.OK
    corpo = resp.json()
    assert corpo['status'] == 'warning'
    assert corpo['message'] == 'nome_divergente'
    assert corpo['errors'] == {
        'nome_ata': 'OUTRA PESSOA',
        'nome_sistema': 'JOSÉ AÇÃO DA SILVA',
    }
    assert corpo['data']['dados_extraidos']['letra_finalidade'] == 'A'


async def test_extrair_vazio_sinaliza_extracao_vazia(
    client, token, militar, storage, extracao
):
    extracao.update(
        letra_finalidade=None, data_realizacao=None, validade_inspsau=None
    )

    resp = await _extrair(client, token, militar.id)

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['extracao_vazia'] is True


async def test_extrair_nao_pdf_400(client, token, militar, extracao):
    resp = await _extrair(client, token, militar.id, nome='ata.txt')

    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert extracao['_chamadas'] == []


# ── GET ───────────────────────────────────────────────────────────


async def test_get_lista_com_url_assinada_mais_recente_primeiro(
    client, session, token, militar, storage
):
    # `created_at` à mão: o id MAIOR é a ata mais ANTIGA, então só ordenar
    # por `created_at desc` produz esta ordem (nem id desc, nem asc).
    nova = await _mk_ata(
        session,
        storage,
        militar.id,
        letra_finalidade='B',
        created_at=datetime(2026, 9, 1),
    )
    velha = await _mk_ata(
        session,
        storage,
        militar.id,
        letra_finalidade='A',
        created_at=datetime(2026, 1, 1),
    )
    assert velha.id > nova.id

    resp = await client.get(f'{URL}user/{militar.id}', headers=_auth(token))

    assert resp.status_code == HTTPStatus.OK
    dados = resp.json()['data']
    assert [a['id'] for a in dados] == [nova.id, velha.id]
    assert (
        dados[0]['url'] == f'https://storage.test/aeromedica/{nova.file_path}'
    )
    assert dados[0]['letra_finalidade'] == 'B'
    assert dados[0]['validade_inspsau'] == VALIDADE.isoformat()


async def test_get_so_traz_atas_do_militar(
    client, session, token, militar, storage
):
    outro = UserFactory(unidade='11gt')
    session.add(outro)
    await session.commit()
    await session.refresh(outro)
    minha = await _mk_ata(session, storage, militar.id)
    await _mk_ata(session, storage, outro.id)

    resp = await client.get(f'{URL}user/{militar.id}', headers=_auth(token))

    assert [a['id'] for a in resp.json()['data']] == [minha.id]


async def test_get_militar_sem_atas_lista_vazia(
    client, token, militar, storage
):
    resp = await client.get(f'{URL}user/{militar.id}', headers=_auth(token))

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data'] == []


# ── PATCH ─────────────────────────────────────────────────────────


async def test_patch_feliz_atualiza_ata_cemal_e_log(
    client, session, token, users, militar, storage
):
    user, _ = users
    ata = await _mk_ata(session, storage, militar.id)
    await _mk_cartao(session, militar.id, date(2026, 1, 1))

    resp = await client.patch(
        f'{URL}{ata.id}',
        json={
            'letra_finalidade': 'B',
            'data_realizacao': '2026-06-01',
            'validade_inspsau': '2029-06-01',
        },
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    corpo = resp.json()
    assert corpo['message'] == 'Ata atualizada com sucesso'
    assert corpo['data']['letra_finalidade'] == 'B'
    assert corpo['data']['validade_inspsau'] == '2029-06-01'

    [depois] = await _atas(session, militar.id)
    assert depois.letra_finalidade == 'B'
    assert depois.data_realizacao == date(2026, 6, 1)
    assert depois.validade_inspsau == date(2029, 6, 1)
    assert (await _cartao(session, militar.id)).cemal == date(2029, 6, 1)

    [log] = await _logs(session, 'ata_update')
    assert log.user_id == user.id
    assert log.resource_id == militar.id
    assert json.loads(log.before) == {
        'letra_finalidade': 'A',
        'data_realizacao': REALIZACAO.isoformat(),
        'validade_inspsau': VALIDADE.isoformat(),
    }
    assert json.loads(log.after) == {
        'letra_finalidade': 'B',
        'data_realizacao': '2026-06-01',
        'validade_inspsau': '2029-06-01',
        'cemal': '2029-06-01',
    }


async def test_patch_validade_menor_nao_regride_cemal(
    client, session, token, militar, storage
):
    ata = await _mk_ata(session, storage, militar.id)
    await _mk_cartao(session, militar.id, date(2030, 1, 1))

    resp = await client.patch(
        f'{URL}{ata.id}',
        json={'validade_inspsau': '2028-01-01'},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    [depois] = await _atas(session, militar.id)
    assert depois.validade_inspsau == date(2028, 1, 1)
    assert (await _cartao(session, militar.id)).cemal == date(2030, 1, 1)
    [log] = await _logs(session, 'ata_update')
    assert 'cemal' not in json.loads(log.after)


async def test_patch_cria_cartao_quando_nao_existe(
    client, session, token, militar, storage
):
    ata = await _mk_ata(session, storage, militar.id, validade_inspsau=None)

    resp = await client.patch(
        f'{URL}{ata.id}',
        json={'validade_inspsau': '2029-06-01'},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    assert (await _cartao(session, militar.id)).cemal == date(2029, 6, 1)
    [log] = await _logs(session, 'ata_update')
    after = json.loads(log.after)
    assert after['cartao_criado'] is True
    assert after['cemal'] == '2029-06-01'


async def test_patch_para_valores_de_outra_ata_409(
    client, session, token, militar, storage
):
    await _mk_ata(session, storage, militar.id)
    outra = await _mk_ata(
        session, storage, militar.id, validade_inspsau=date(2030, 1, 1)
    )

    resp = await client.patch(
        f'{URL}{outra.id}',
        json={
            'letra_finalidade': 'A',
            'data_realizacao': REALIZACAO.isoformat(),
            'validade_inspsau': VALIDADE.isoformat(),
        },
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.CONFLICT
    [_, depois] = await _atas(session, militar.id)
    assert depois.validade_inspsau == date(2030, 1, 1)
    assert await _logs(session, 'ata_update') == []


async def test_patch_com_os_proprios_valores_nao_e_duplicata_nem_evento(
    client, session, token, militar, storage
):
    ata = await _mk_ata(session, storage, militar.id)
    await _mk_cartao(session, militar.id, VALIDADE)

    resp = await client.patch(
        f'{URL}{ata.id}',
        json={
            'letra_finalidade': 'A',
            'data_realizacao': REALIZACAO.isoformat(),
            'validade_inspsau': VALIDADE.isoformat(),
        },
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    assert await _logs(session, 'ata_update') == []


async def test_patch_valores_identicos_que_empurra_cemal_gera_log(
    client, session, token, militar, storage
):
    """`or efeito_cartao`: correção sem delta na ata, mas com escrita no
    cartão, precisa entrar na trilha."""
    ata = await _mk_ata(session, storage, militar.id)
    await _mk_cartao(session, militar.id, date(2026, 1, 1))

    resp = await client.patch(
        f'{URL}{ata.id}',
        json={
            'letra_finalidade': 'A',
            'data_realizacao': REALIZACAO.isoformat(),
            'validade_inspsau': VALIDADE.isoformat(),
        },
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    assert (await _cartao(session, militar.id)).cemal == VALIDADE
    [log] = await _logs(session, 'ata_update')
    assert log.resource_id == militar.id
    assert json.loads(log.before) == {}
    assert json.loads(log.after) == {'cemal': VALIDADE.isoformat()}


async def test_patch_ata_inexistente_404(client, token, storage):
    resp = await client.patch(
        f'{URL}999999',
        json={'letra_finalidade': 'B'},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.NOT_FOUND


async def test_patch_letra_com_mais_de_um_caractere_422(
    client, session, token, militar, storage
):
    ata = await _mk_ata(session, storage, militar.id)

    resp = await client.patch(
        f'{URL}{ata.id}',
        json={'letra_finalidade': 'AB'},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


# ── DELETE ────────────────────────────────────────────────────────


async def test_delete_feliz_remove_linha_arquivo_e_registra_log(
    client, session, token, users, militar, storage
):
    user, _ = users
    ata = await _mk_ata(session, storage, militar.id)
    mantida = await _mk_ata(session, storage, militar.id, letra_finalidade='B')

    resp = await client.delete(f'{URL}{ata.id}', headers=_auth(token))

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['message'] == 'Ata removida com sucesso'
    [restante] = await _atas(session, militar.id)
    assert restante.id == mantida.id
    assert list(storage) == [mantida.file_path]

    [log] = await _logs(session, 'ata_delete')
    assert log.user_id == user.id
    assert log.resource_id == militar.id
    assert json.loads(log.before) == {
        'file_name': 'x.pdf',
        'letra_finalidade': 'A',
        'data_realizacao': REALIZACAO.isoformat(),
        'validade_inspsau': VALIDADE.isoformat(),
    }


async def test_delete_falha_no_storage_nao_impede_remocao(
    client, session, token, militar, storage, monkeypatch
):
    ata = await _mk_ata(session, storage, militar.id)

    def explode(bucket, path):
        raise OSError('storage fora')

    monkeypatch.setattr(atas, 'delete_file', explode)

    resp = await client.delete(f'{URL}{ata.id}', headers=_auth(token))

    assert resp.status_code == HTTPStatus.OK
    assert await _atas(session, militar.id) == []
    assert len(await _logs(session, 'ata_delete')) == 1


async def test_delete_ata_inexistente_404(client, token, storage):
    resp = await client.delete(f'{URL}999999', headers=_auth(token))

    assert resp.status_code == HTTPStatus.NOT_FOUND


# ── PATCH parcial ─────────────────────────────────────────────────


async def test_patch_parcial_preserva_campos_omitidos(
    client, session, token, militar, storage
):
    """Só o que vem no corpo muda: corrigir a letra não zera data nem
    validade (antes o PATCH era substituição total e apagava os dois). O
    CEMAL foi baixado à mão: corrigir a letra não reaplica a validade."""
    ata = await _mk_ata(session, storage, militar.id)
    await _mk_cartao(session, militar.id, date(2027, 1, 1))

    resp = await client.patch(
        f'{URL}{ata.id}',
        json={'letra_finalidade': 'B'},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    [depois] = await _atas(session, militar.id)
    assert depois.letra_finalidade == 'B'
    assert depois.data_realizacao == REALIZACAO
    assert depois.validade_inspsau == VALIDADE
    assert (await _cartao(session, militar.id)).cemal == date(2027, 1, 1)
    [log] = await _logs(session, 'ata_update')
    assert json.loads(log.before) == {'letra_finalidade': 'A'}
    assert json.loads(log.after) == {'letra_finalidade': 'B'}


async def test_patch_null_explicito_limpa_o_campo(
    client, session, token, militar, storage
):
    ata = await _mk_ata(session, storage, militar.id)

    resp = await client.patch(
        f'{URL}{ata.id}',
        json={'letra_finalidade': None},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    [depois] = await _atas(session, militar.id)
    assert depois.letra_finalidade is None
    assert depois.validade_inspsau == VALIDADE


async def test_patch_corpo_vazio_nao_altera_nada(
    client, session, token, militar, storage
):
    ata = await _mk_ata(session, storage, militar.id)
    await _mk_cartao(session, militar.id, date(2027, 1, 1))

    resp = await client.patch(f'{URL}{ata.id}', json={}, headers=_auth(token))

    assert resp.status_code == HTTPStatus.OK
    [depois] = await _atas(session, militar.id)
    assert (
        depois.letra_finalidade,
        depois.data_realizacao,
        depois.validade_inspsau,
    ) == ('A', REALIZACAO, VALIDADE)
    assert (await _cartao(session, militar.id)).cemal == date(2027, 1, 1)
    assert await _logs(session, 'ata_update') == []


async def test_patch_sem_mudanca_nao_da_409_por_copia_existente(
    client, session, token, militar, storage
):
    """Duas atas iguais já gravadas (dado antigo ou corrida — a duplicata é
    check-then-insert): reenviar os valores de uma delas não muda nada e
    não pode responder 409."""
    await _mk_ata(session, storage, militar.id)
    copia = await _mk_ata(session, storage, militar.id)

    resp = await client.patch(
        f'{URL}{copia.id}',
        json={'letra_finalidade': 'A'},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK


async def test_patch_parcial_checa_duplicata_pelo_estado_mesclado(
    client, session, token, militar, storage
):
    """Trocar só a letra de B para A deixaria esta ata igual à outra (mesma
    data e validade): a duplicata tem de olhar a ata como vai ficar, não o
    corpo sozinho — que, com os demais campos nulos, não colide com nada."""
    await _mk_ata(session, storage, militar.id)
    outra = await _mk_ata(session, storage, militar.id, letra_finalidade='B')

    resp = await client.patch(
        f'{URL}{outra.id}',
        json={'letra_finalidade': 'A'},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.CONFLICT
    [_, depois] = await _atas(session, militar.id)
    assert depois.letra_finalidade == 'B'


# ── Chave do objeto e falha pós-commit ────────────────────────────


async def test_upload_no_mesmo_segundo_grava_objetos_distintos(
    client, session, token, militar, storage, monkeypatch
):
    """Dois uploads do mesmo militar no mesmo segundo e com a mesma data de
    realização (só a letra muda) caíam na mesma chave: o segundo PDF
    sobrescrevia o primeiro e excluir uma ata apagava o arquivo da outra."""

    # Relógio parado só no router (não `freeze_time`, que troca o
    # `datetime` global e pode quebrar a montagem dos schemas do FastAPI).
    class RelogioParado(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC)

    monkeypatch.setattr(atas, 'datetime', RelogioParado)
    for letra in ('A', 'B'):
        resp = await _enviar(
            client,
            token,
            militar.id,
            conteudo=_pdf(letra.encode()),
            dados_confirmados=True,
            conf_letra=letra,
            conf_realizacao=REALIZACAO.isoformat(),
            conf_validade=VALIDADE.isoformat(),
        )
        assert resp.status_code == HTTPStatus.CREATED

    primeira, segunda = await _atas(session, militar.id)
    assert primeira.file_path != segunda.file_path
    assert storage[primeira.file_path] != storage[segunda.file_path]

    resp = await client.delete(f'{URL}{primeira.id}', headers=_auth(token))

    assert resp.status_code == HTTPStatus.OK
    assert segunda.file_path in storage


async def test_upload_falha_apos_o_commit_preserva_o_objeto(
    client, session, token, militar, storage, extracao, monkeypatch
):
    """Depois do commit a linha existe e aponta para o objeto: uma falha
    dali em diante (aqui, no `refresh`) não pode apagá-lo do storage, ou a
    ata fica gravada apontando para um PDF inexistente."""

    async def explode(*args, **kwargs):
        raise RuntimeError('conexão caiu')

    monkeypatch.setattr(session, 'refresh', explode)

    with pytest.raises(RuntimeError, match='conexão caiu'):
        await _enviar(client, token, militar.id)

    [ata] = await _atas(session, militar.id)
    assert list(storage) == [ata.file_path]
