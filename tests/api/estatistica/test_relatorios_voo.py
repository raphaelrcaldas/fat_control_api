"""Relatórios de voo (/estatistica/relatorios-voo).

Storage e Ghostscript são trocados por fakes no namespace do router: o teste
não depende de MinIO nem de `gs`. Seeds: '11gt' opera o projeto C8; '1gt'
opera o C1.
"""

import hashlib
from datetime import date, timedelta
from http import HTTPStatus

import pytest
from botocore.exceptions import EndpointConnectionError
from freezegun import freeze_time
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.app import app
from fcontrol_api.models.estatistica.relatorio_voo import RelatorioVoo
from fcontrol_api.models.security.logs import UserActionLog
from fcontrol_api.models.security.resources import UserRole
from fcontrol_api.models.shared.aeronaves import Aeronave
from fcontrol_api.routers.estatistica import relatorios_voo

pytestmark = pytest.mark.anyio

# `freeze_time` troca `datetime`/`date` globalmente; se isso acontecer antes
# do FastAPI montar (na 1ª requisição do processo) os schemas Pydantic de
# ALGUMA rota que usa `date`, o `isinstance` interno do Pydantic quebra com
# `FastAPIError: Invalid args for response field!` numa rota qualquer, sem
# relação com este teste. Força a montagem antes de qualquer `freeze_time`.
app.openapi()

URL = '/estatistica/relatorios-voo/'
LOG_RESOURCE = 'estatistica.relatorios_voo'
NAO_ENCONTRADO = relatorios_voo.NAO_ENCONTRADO


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def _pdf(marca: str) -> bytes:
    """PDF mínimo; `marca` torna o sha256 único por teste."""
    return b'%PDF-1.4\n%' + marca.encode() + b'\n%%EOF\n'


@pytest.fixture
def storage(monkeypatch):
    """Bucket em memória + compressão/contagem neutras."""
    objetos: dict[str, bytes] = {}

    def fake_upload(bucket, path, data, content_type, size):
        objetos[path] = data

    def fake_delete(bucket, path):
        objetos.pop(path, None)

    def fake_url(bucket, path, expires=900, content_disposition=None):
        return f'https://storage.test/{bucket}/{path}'

    monkeypatch.setattr(relatorios_voo, 'upload_file', fake_upload)
    monkeypatch.setattr(relatorios_voo, 'delete_file', fake_delete)
    monkeypatch.setattr(relatorios_voo, 'get_signed_url', fake_url)
    monkeypatch.setattr(relatorios_voo, 'comprimir_pdf', lambda c: c)
    monkeypatch.setattr(relatorios_voo, 'contar_paginas', lambda c: 2)
    return objetos


@pytest.fixture
async def frota(session):
    """2850 (C8, 11gt), 2851 simulador (C8), 1301 (C1, 1gt)."""
    session.add_all([
        Aeronave(matricula='2850', active=True, sit='DI', obs=None),
        Aeronave(
            matricula='2851', active=True, sit='DI', obs=None, is_sim=True
        ),
        Aeronave(
            matricula='1301', active=True, sit='DI', obs=None, projeto='C1'
        ),
    ])
    await session.commit()


@pytest.fixture
async def admin_1gt_token(users, session, make_org_token):
    """Token com org ativa '1gt' e vínculo admin nessa org."""
    _, other = users
    session.add(UserRole(user_id=other.id, role_id=1, organizacao_id='1gt'))
    await session.commit()
    return await make_org_token(other, active_org='1gt')


async def _enviar(client, token, *, anv='2850', dia='2026-09-20', marca='a'):
    return await client.post(
        URL,
        files={'file': ('scan.pdf', _pdf(marca), 'application/pdf')},
        data={'anv': anv, 'data': dia},
        headers=_auth(token),
    )


# ── POST ──────────────────────────────────────────────────────────


async def test_upload_cria_registro_e_objeto(client, token, frota, storage):
    resp = await _enviar(client, token)

    assert resp.status_code == HTTPStatus.CREATED
    corpo = resp.json()['data']
    assert corpo['anv'] == '2850'
    assert corpo['data'] == '2026-09-20'
    assert corpo['seq'] == 1
    assert corpo['file_path'] == '11gt/2026/2850_2026-09-20.pdf'
    assert corpo['num_paginas'] == 2
    assert corpo['file_name'] == 'scan.pdf'
    assert '11gt/2026/2850_2026-09-20.pdf' in storage


async def test_segundo_do_dia_recebe_sufixo(client, token, frota, storage):
    await _enviar(client, token, marca='a')
    resp = await _enviar(client, token, marca='b')

    assert resp.status_code == HTTPStatus.CREATED
    assert resp.json()['data']['seq'] == 2
    assert resp.json()['data']['file_path'] == (
        '11gt/2026/2850_2026-09-20_2.pdf'
    )


async def test_arquivo_identico_409_com_existente(
    client, token, frota, storage
):
    primeiro = (await _enviar(client, token, marca='x')).json()['data']
    resp = await _enviar(client, token, marca='x')

    assert resp.status_code == HTTPStatus.CONFLICT
    corpo = resp.json()
    assert corpo['message'] == 'Arquivo idêntico já enviado'
    assert corpo['errors'] == {
        'id': primeiro['id'],
        'anv': '2850',
        'data': '2026-09-20',
        'file_path': '11gt/2026/2850_2026-09-20.pdf',
    }
    assert len(storage) == 1


async def test_mesmo_arquivo_em_outra_unidade_e_aceito(
    client, token, admin_1gt_token, frota, storage
):
    await _enviar(client, token, anv='2850', marca='y')
    resp = await _enviar(client, admin_1gt_token, anv='1301', marca='y')

    assert resp.status_code == HTTPStatus.CREATED
    assert resp.json()['data']['file_path'].startswith('1gt/')


@pytest.mark.parametrize(
    ('nome', 'conteudo', 'mensagem'),
    [
        ('scan.jpg', b'%PDF-1.4', 'Apenas arquivos PDF são permitidos'),
        ('scan.pdf', b'GIF89a', 'Arquivo não é um PDF válido'),
    ],
)
async def test_arquivo_invalido_400(
    client, token, frota, storage, nome, conteudo, mensagem
):
    resp = await client.post(
        URL,
        files={'file': (nome, conteudo, 'application/pdf')},
        data={'anv': '2850', 'data': '2026-09-20'},
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert resp.json()['message'] == mensagem


async def test_arquivo_grande_400(client, token, frota, storage):
    grande = b'%PDF-1.4\n' + b'0' * (10 * 1024 * 1024)
    resp = await client.post(
        URL,
        files={'file': ('scan.pdf', grande, 'application/pdf')},
        data={'anv': '2850', 'data': '2026-09-20'},
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert resp.json()['message'] == 'Arquivo excede o limite de 10 MB'


@pytest.mark.parametrize('anv', ['1301', '2851', '9999'])
async def test_aeronave_fora_da_frota_400(client, token, frota, storage, anv):
    """1301 é de outra unidade, 2851 é simulador, 9999 não existe."""
    resp = await _enviar(client, token, anv=anv)
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert resp.json()['message'] == (
        f'Aeronave {anv} não pertence à frota da unidade'
    )


async def test_data_futura_422(client, token, frota, storage):
    amanha = (date.today() + timedelta(days=2)).isoformat()
    resp = await _enviar(client, token, dia=amanha)
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_data_de_hoje_em_brasilia_aceita_as_22h_utc(
    client, token, frota, storage
):
    """22h UTC de 20/09 é 19h de 20/09 em Brasília: "hoje" é o mesmo dia.

    Não regressão: ao passar a usar o fuso de Brasília, a regra não pode
    endurecer à noite. A regressão do fuso em si é o caso das 2h UTC, abaixo.
    """
    with freeze_time('2026-09-20 22:00:00'):
        resp = await _enviar(client, token, dia='2026-09-20')
    assert resp.status_code == HTTPStatus.CREATED


async def test_data_de_amanha_em_brasilia_e_futura_as_2h_utc(
    client, token, frota, storage
):
    """2h UTC de 21/09 é 23h de 20/09 em Brasília: 21/09 ainda é futuro.

    Sem o fuso explícito, `date.today()` em UTC já leria 21/09 e aceitaria a
    data indevidamente.
    """
    with freeze_time('2026-09-21 02:00:00'):
        resp = await _enviar(client, token, dia='2026-09-21')
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_falha_no_bucket_nao_grava_linha(
    client, token, frota, storage, monkeypatch
):
    """503 e bucket intocado.

    Não se relê o banco depois: a sessão de teste é ligada a uma transação
    externa (`tests/conftest.py`) e o `session.rollback()` do handler desfaz
    essa transação inteira — fixtures incluídas. O rollback em si é o que
    garante "nenhuma linha"; aqui se prova o 503 e que nada subiu.
    """

    def bucket_fora(*args, **kwargs):
        raise EndpointConnectionError(endpoint_url='http://storage')

    monkeypatch.setattr(relatorios_voo, 'upload_file', bucket_fora)
    resp = await _enviar(client, token)

    assert resp.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert resp.json()['message'] == (
        'Armazenamento indisponível; nada foi alterado. Tente novamente.'
    )
    assert storage == {}


async def test_falha_no_commit_remove_objeto_orfao_do_bucket(
    client, token, frota, storage, monkeypatch
):
    """`session.commit()` falha depois do upload: o objeto não fica órfão.

    Prova a compensação do POST: quando o commit falha, o objeto já enviado
    ao bucket é apagado. O handler não trata `SQLAlchemyError`, então ela
    propaga; o teste captura essa propagação e confere o bucket.
    """

    async def commit_falho(self, *args, **kwargs):
        raise OperationalError('commit', {}, Exception('conexão perdida'))

    monkeypatch.setattr(AsyncSession, 'commit', commit_falho)

    with pytest.raises(OperationalError):
        await _enviar(client, token)

    assert storage == {}


async def test_upload_grava_log(client, session, token, frota, storage):
    corpo = (await _enviar(client, token)).json()['data']
    log = await session.scalar(
        select(UserActionLog).where(
            UserActionLog.resource == LOG_RESOURCE,
            UserActionLog.resource_id == corpo['id'],
            UserActionLog.action == 'create',
        )
    )
    assert log is not None


async def test_corrida_no_flush_devolve_409_estruturado(
    client, session, token, users, frota, storage, monkeypatch
):
    """Corrida: outro envio do mesmo arquivo entra entre a 1ª checagem de
    sha256 (antes do laço) e o flush da 1ª tentativa.

    Não há como commitar a linha concorrente por uma segunda conexão real —
    `frota` (a aeronave '2850') existe só dentro da transação externa deste
    teste (`tests/conftest.py`); uma segunda engine não a enxergaria e o
    INSERT concorrente bateria em `relatorios_voo_anv_fkey`. Em vez disso,
    simula-se a corrida na MESMA sessão, mas com um `commit()` de verdade: no
    ponto do primeiro `flush()` do handler, insere-se a linha concorrente e
    comita-se antes de levantar `IntegrityError` — o mesmo erro que a unique
    de seq ou de sha256 dispararia numa corrida real. Esse `commit()` NÃO
    escapa da transação externa do teste (`conftest.py:91-110`): a `session`
    está ligada a uma `connection` cuja transação de verdade já foi aberta
    por fora (`connection.begin()`); o `commit()` da `Session` só encerra o
    bloco de transação que ela mesma abriu implicitamente sobre essa
    conexão compartilhada, e o `transaction.rollback()` do fixture, no fim
    do teste, desfaz tudo — inclusive a linha concorrente. O handler faz
    rollback (da transação nova, vazia) e, na 2ª tentativa, repete a
    checagem de sha256: encontra a linha concorrente (ainda visível dentro
    desta mesma sessão/transação) e devolve o 409 estruturado, não o
    genérico de seq.
    """
    conteudo = _pdf('corrida')
    sha256 = hashlib.sha256(conteudo).hexdigest()
    autor_id = users[0].id

    def relatorio_pendente(sessao):
        # O `relatorio` (seq=1) que o handler monta antes de chamar
        # `flush()`: precisa sair da sessão antes do commit abaixo, senão
        # entra no autoflush e colide por seq com a concorrente — testaria a
        # colisão errada.
        (obj,) = (o for o in sessao.new if isinstance(o, RelatorioVoo))
        return obj

    flush_original = AsyncSession.flush
    chamadas = {'n': 0}
    concorrente_id = {}

    async def flush_com_colisao_na_primeira(self, *args, **kwargs):
        chamadas['n'] += 1
        if chamadas['n'] == 1:
            pendente = relatorio_pendente(self)
            self.expunge(pendente)
            concorrente = RelatorioVoo(
                uae='11gt',
                anv='2850',
                data=date(2026, 9, 20),
                seq=1,
                file_path='11gt/2026/2850_2026-09-20.pdf',
                file_name='concorrente.pdf',
                file_size=len(conteudo),
                sha256=sha256,
                uploaded_by=autor_id,
                num_paginas=1,
                obs=None,
            )
            self.add(concorrente)
            await self.commit()
            concorrente_id['v'] = concorrente.id
            self.add(pendente)
            raise IntegrityError('flush', {}, Exception('colisão simulada'))
        return await flush_original(self, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, 'flush', flush_com_colisao_na_primeira)

    resp = await client.post(
        URL,
        files={'file': ('scan.pdf', conteudo, 'application/pdf')},
        data={'anv': '2850', 'data': '2026-09-20'},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.CONFLICT
    corpo = resp.json()
    assert corpo['message'] == 'Arquivo idêntico já enviado'
    assert corpo['errors'] == {
        'id': concorrente_id['v'],
        'anv': '2850',
        'data': '2026-09-20',
        'file_path': '11gt/2026/2850_2026-09-20.pdf',
    }


# ── GET lista ────────────────────────────────────────────────────────────


async def test_lista_do_periodo_so_da_org_ativa(
    client, token, admin_1gt_token, frota, storage
):
    await _enviar(client, token, dia='2026-09-01', marca='ini')
    await _enviar(client, token, dia='2026-09-15', marca='a')
    await _enviar(client, token, dia='2026-09-20', marca='fim')
    await _enviar(client, token, dia='2026-08-31', marca='b')
    await _enviar(client, token, dia='2026-09-21', marca='depois')
    await _enviar(client, admin_1gt_token, anv='1301', marca='c')

    resp = await client.get(
        URL,
        params={'data_ini': '2026-09-01', 'data_fim': '2026-09-20'},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    corpo = resp.json()['data']
    assert [i['data'] for i in corpo['itens']] == [
        '2026-09-20',
        '2026-09-15',
        '2026-09-01',
    ]
    assert corpo['itens'][0]['uploaded_by_nome_guerra']
    assert corpo['contagem_por_anv'] == {'2850': 3}


async def test_lista_periodo_de_um_dia(client, token, frota, storage):
    """`data_ini == data_fim`: uso da futura fila do digitalizador."""
    await _enviar(client, token, dia='2026-09-19', marca='antes')
    await _enviar(client, token, dia='2026-09-20', marca='a')
    await _enviar(client, token, dia='2026-09-20', marca='b')
    await _enviar(client, token, dia='2026-09-21', marca='depois')

    resp = await client.get(
        URL,
        params={'data_ini': '2026-09-20', 'data_fim': '2026-09-20'},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    corpo = resp.json()['data']
    assert [i['data'] for i in corpo['itens']] == [
        '2026-09-20',
        '2026-09-20',
    ]


async def test_lista_ordena_por_data_e_id_desc(client, token, frota, storage):
    await _enviar(client, token, dia='2026-09-10', marca='a')
    await _enviar(client, token, dia='2026-09-20', marca='b')
    await _enviar(client, token, dia='2026-09-20', marca='c')

    resp = await client.get(
        URL,
        params={'data_ini': '2026-09-01', 'data_fim': '2026-09-30'},
        headers=_auth(token),
    )

    seqs = [(i['data'], i['seq']) for i in resp.json()['data']['itens']]
    assert seqs == [('2026-09-20', 2), ('2026-09-20', 1), ('2026-09-10', 1)]


async def test_filtro_anv_nao_muda_contagem(client, token, session, storage):
    session.add_all([
        Aeronave(matricula='2850', active=True, sit='DI', obs=None),
        Aeronave(matricula='2855', active=True, sit='DI', obs=None),
    ])
    await session.commit()
    await _enviar(client, token, anv='2850', marca='a')
    await _enviar(client, token, anv='2855', marca='b')

    resp = await client.get(
        URL,
        params={
            'data_ini': '2026-09-01',
            'data_fim': '2026-09-30',
            'anv': '2855',
        },
        headers=_auth(token),
    )

    corpo = resp.json()['data']
    assert [i['anv'] for i in corpo['itens']] == ['2855']
    assert corpo['contagem_por_anv'] == {'2850': 1, '2855': 1}


@pytest.mark.parametrize(
    'params',
    [
        {},
        {'data_ini': '2026-09-01'},
        {'data_fim': '2026-09-30'},
        {'data_ini': '2026-09-31', 'data_fim': '2026-09-30'},
    ],
)
async def test_periodo_obrigatorio_e_valido_422(client, token, params):
    resp = await client.get(URL, params=params, headers=_auth(token))
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_periodo_invertido_422_com_mensagem(client, token):
    resp = await client.get(
        URL,
        params={'data_ini': '2026-09-30', 'data_fim': '2026-09-01'},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resp.json()['message'] == (
        'A data inicial não pode ser posterior à data final'
    )


# ── GET arquivo ──────────────────────────────────────────────────


async def test_arquivo_devolve_url(client, token, frota, storage):
    rel = (await _enviar(client, token)).json()['data']

    resp = await client.get(f'{URL}{rel["id"]}/arquivo', headers=_auth(token))

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['url'].endswith(rel['file_path'])


async def test_arquivo_de_outra_org_404(
    client, token, admin_1gt_token, frota, storage
):
    rel = (await _enviar(client, admin_1gt_token, anv='1301')).json()['data']

    resp = await client.get(f'{URL}{rel["id"]}/arquivo', headers=_auth(token))

    assert resp.status_code == HTTPStatus.NOT_FOUND
    assert resp.json()['message'] == NAO_ENCONTRADO


# ── PATCH / DELETE ───────────────────────────────────────────────


async def test_patch_altera_so_obs_e_loga(
    client, session, token, frota, storage
):
    rel = (await _enviar(client, token)).json()['data']

    resp = await client.patch(
        f'{URL}{rel["id"]}',
        json={'obs': '  translado  '},
        headers=_auth(token),
    )

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['obs'] == 'translado'
    assert resp.json()['data']['anv'] == '2850'
    log = await session.scalar(
        select(UserActionLog).where(
            UserActionLog.resource == LOG_RESOURCE,
            UserActionLog.action == 'update',
        )
    )
    assert log is not None


async def test_patch_vazio_limpa_obs(client, token, frota, storage):
    rel = (await _enviar(client, token)).json()['data']
    await client.patch(
        f'{URL}{rel["id"]}', json={'obs': 'x'}, headers=_auth(token)
    )

    resp = await client.patch(
        f'{URL}{rel["id"]}', json={'obs': ''}, headers=_auth(token)
    )

    assert resp.json()['data']['obs'] is None


async def test_patch_sem_campo_obs_e_422(client, token, frota, storage):
    """`obs` é obrigatório no corpo (mesmo aceitando `null`): sem ele, o
    PATCH não pode silenciosamente apagar a observação existente."""
    rel = (await _enviar(client, token)).json()['data']

    resp = await client.patch(
        f'{URL}{rel["id"]}', json={}, headers=_auth(token)
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_patch_com_obs_null_limpa_observacao(
    client, token, frota, storage
):
    rel = (await _enviar(client, token)).json()['data']
    await client.patch(
        f'{URL}{rel["id"]}', json={'obs': 'translado'}, headers=_auth(token)
    )

    resp = await client.patch(
        f'{URL}{rel["id"]}', json={'obs': None}, headers=_auth(token)
    )

    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['obs'] is None


async def test_delete_remove_linha_e_objeto(client, token, frota, storage):
    rel = (await _enviar(client, token)).json()['data']

    resp = await client.delete(f'{URL}{rel["id"]}', headers=_auth(token))

    assert resp.status_code == HTTPStatus.OK
    assert rel['file_path'] not in storage
    assert resp.json()['message'] == 'Relatório excluído'
    depois = await client.get(
        f'{URL}{rel["id"]}/arquivo', headers=_auth(token)
    )
    assert depois.status_code == HTTPStatus.NOT_FOUND


async def test_sufixo_nao_reaproveita_numero_apagado(
    client, token, frota, storage
):
    primeiro = (await _enviar(client, token, marca='a')).json()['data']
    await _enviar(client, token, marca='b')
    apagou = await client.delete(
        f'{URL}{primeiro["id"]}', headers=_auth(token)
    )
    assert apagou.status_code == HTTPStatus.OK

    resp = await _enviar(client, token, marca='c')

    assert resp.json()['data']['seq'] == 3
    assert resp.json()['data']['file_path'].endswith('_3.pdf')


async def test_falha_no_bucket_preserva_relatorio(
    client, token, frota, storage, monkeypatch
):
    """503 e o objeto continua no bucket.

    Como em `test_falha_no_bucket_nao_grava_linha`, o banco não é relido: o
    rollback do handler desfaz a transação externa do teste. Em produção é
    esse rollback que devolve a linha (a exclusão só tinha sido `flush`).
    """
    rel = (await _enviar(client, token)).json()['data']

    def bucket_fora(*args, **kwargs):
        raise EndpointConnectionError(endpoint_url='http://storage')

    monkeypatch.setattr(relatorios_voo, 'delete_file', bucket_fora)
    resp = await client.delete(f'{URL}{rel["id"]}', headers=_auth(token))

    assert resp.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert rel['file_path'] in storage


@pytest.mark.parametrize('metodo', ['patch', 'delete'])
async def test_escrita_em_outra_org_404(
    client, token, admin_1gt_token, frota, storage, metodo
):
    rel = (await _enviar(client, admin_1gt_token, anv='1301')).json()['data']
    kwargs = {'json': {'obs': 'x'}} if metodo == 'patch' else {}
    storage_antes = dict(storage)

    resp = await getattr(client, metodo)(
        f'{URL}{rel["id"]}', headers=_auth(token), **kwargs
    )

    assert resp.status_code == HTTPStatus.NOT_FOUND
    assert resp.json()['message'] == NAO_ENCONTRADO
    if metodo == 'delete':
        assert storage == storage_antes
