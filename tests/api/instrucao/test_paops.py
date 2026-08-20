"""PAOP: plano anual, seus subprogramas e as matrículas (/instrucao/paops).

Um plano por unidade por ano (uq uae+ano). O plano só aceita subprograma da
própria unidade, e a matrícula só aceita tripulante ativo da unidade **e da
função do subprograma**.
"""

from datetime import date
from http import HTTPStatus

import pytest

from fcontrol_api.models.instrucao.subprogramas import Paop, Subprograma
from tests.factories import TripFactory, UserFactory

pytestmark = pytest.mark.anyio

URL = '/instrucao/paops/'


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


async def _mk_subprograma(
    session, *, uae='11gt', codigo='SPFO-01', func='pil'
):
    subprograma = Subprograma(
        uae=uae,
        codigo=codigo,
        descricao=f'Subprograma {codigo}',
        tipo='Formação',
        func=func,
    )
    session.add(subprograma)
    await session.commit()
    return subprograma


async def _mk_trip(session, *, uae='11gt', func='pil', active=True):
    user = UserFactory(unidade=uae)
    session.add(user)
    await session.flush()
    trip = TripFactory(user_id=user.id, uae=uae, func=func)
    trip.active = active
    session.add(trip)
    await session.commit()
    return trip


@pytest.fixture
async def paop(client, token):
    resp = await client.post(URL, headers=_auth(token), json={'ano': 2026})
    assert resp.status_code == HTTPStatus.CREATED
    return resp.json()['data']


async def test_create_assume_ano_civil(paop):
    assert paop['data_ini'] == '2026-01-01'
    assert paop['data_fim'] == '2026-12-31'
    assert paop['status'] == 'rascunho'
    assert paop['total_subprogramas'] == 0


async def test_create_aceita_janela_propria(client, token):
    resp = await client.post(
        URL,
        headers=_auth(token),
        json={
            'ano': 2027,
            'data_ini': '2027-03-01',
            'data_fim': '2027-11-30',
            'status': 'vigente',
        },
    )
    assert resp.status_code == HTTPStatus.CREATED
    assert resp.json()['data']['data_ini'] == '2027-03-01'
    assert resp.json()['data']['status'] == 'vigente'


async def test_um_paop_por_ano(client, token, paop):
    resp = await client.post(URL, headers=_auth(token), json={'ano': 2026})
    assert resp.status_code == HTTPStatus.CONFLICT
    assert resp.json()['message'] == 'Já existe PAOP para 2026'


async def test_janela_invertida_recusada(client, token):
    resp = await client.post(
        URL,
        headers=_auth(token),
        json={
            'ano': 2028,
            'data_ini': '2028-12-01',
            'data_fim': '2028-02-01',
        },
    )
    assert resp.status_code == HTTPStatus.BAD_REQUEST


async def test_janela_invertida_no_update(client, token, paop):
    """Mesma regra do POST e mesmo status — a checagem mora na rota."""
    resp = await client.put(
        f'{URL}{paop["id"]}',
        headers=_auth(token),
        json={
            'data_ini': '2026-12-01',
            'data_fim': '2026-02-01',
            'status': 'vigente',
        },
    )
    assert resp.status_code == HTTPStatus.BAD_REQUEST


async def test_status_fora_da_lista_422(client, token):
    resp = await client.post(
        URL, headers=_auth(token), json={'ano': 2029, 'status': 'arquivado'}
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_update_cabecalho(client, token, paop):
    resp = await client.put(
        f'{URL}{paop["id"]}',
        headers=_auth(token),
        json={
            'data_ini': '2026-02-01',
            'data_fim': '2026-11-30',
            'status': 'encerrado',
        },
    )
    assert resp.status_code == HTTPStatus.OK

    detalhe = await client.get(f'{URL}{paop["id"]}', headers=_auth(token))
    assert detalhe.json()['data']['status'] == 'encerrado'
    assert detalhe.json()['data']['data_ini'] == '2026-02-01'


async def test_ciclo_subprogramas_e_matriculas(client, session, token, paop):
    sp = await _mk_subprograma(session)
    trip = await _mk_trip(session)

    incluir = await client.put(
        f'{URL}{paop["id"]}/subprogramas',
        headers=_auth(token),
        json={'subprograma_ids': [sp.id]},
    )
    assert incluir.status_code == HTTPStatus.OK

    detalhe = await client.get(f'{URL}{paop["id"]}', headers=_auth(token))
    itens = detalhe.json()['data']['subprogramas']
    assert len(itens) == 1
    assert itens[0]['subprograma']['codigo'] == 'SPFO-01'
    assert itens[0]['tripulantes'] == []
    item_id = itens[0]['id']

    matricular = await client.put(
        f'{URL}{paop["id"]}/subprogramas/{item_id}/tripulantes',
        headers=_auth(token),
        json={'trip_ids': [trip.id]},
    )
    assert matricular.status_code == HTTPStatus.OK

    detalhe = await client.get(f'{URL}{paop["id"]}', headers=_auth(token))
    matriculados = detalhe.json()['data']['subprogramas'][0]['tripulantes']
    assert [m['trip_id'] for m in matriculados] == [trip.id]
    assert matriculados[0]['trig'] == trip.trig

    listagem = await client.get(URL, headers=_auth(token))
    linha = next(p for p in listagem.json()['data'] if p['id'] == paop['id'])
    assert linha['total_subprogramas'] == 1
    assert linha['total_matriculas'] == 1

    desmatricular = await client.put(
        f'{URL}{paop["id"]}/subprogramas/{item_id}/tripulantes',
        headers=_auth(token),
        json={'trip_ids': []},
    )
    assert desmatricular.status_code == HTTPStatus.OK

    remover = await client.put(
        f'{URL}{paop["id"]}/subprogramas',
        headers=_auth(token),
        json={'subprograma_ids': []},
    )
    assert remover.status_code == HTTPStatus.OK

    detalhe = await client.get(f'{URL}{paop["id"]}', headers=_auth(token))
    assert detalhe.json()['data']['subprogramas'] == []


async def test_matricula_preserva_data_inclusao(client, session, token, paop):
    """Reenviar o conjunto não recria quem já estava matriculado."""
    sp = await _mk_subprograma(session)
    a = await _mk_trip(session)
    b = await _mk_trip(session)

    await client.put(
        f'{URL}{paop["id"]}/subprogramas',
        headers=_auth(token),
        json={'subprograma_ids': [sp.id]},
    )
    detalhe = await client.get(f'{URL}{paop["id"]}', headers=_auth(token))
    item_id = detalhe.json()['data']['subprogramas'][0]['id']

    await client.put(
        f'{URL}{paop["id"]}/subprogramas/{item_id}/tripulantes',
        headers=_auth(token),
        json={'trip_ids': [a.id]},
    )
    detalhe = await client.get(f'{URL}{paop["id"]}', headers=_auth(token))
    vinculo_a = detalhe.json()['data']['subprogramas'][0]['tripulantes'][0]

    await client.put(
        f'{URL}{paop["id"]}/subprogramas/{item_id}/tripulantes',
        headers=_auth(token),
        json={'trip_ids': [a.id, b.id]},
    )
    detalhe = await client.get(f'{URL}{paop["id"]}', headers=_auth(token))
    matriculados = detalhe.json()['data']['subprogramas'][0]['tripulantes']
    assert len(matriculados) == 2
    mantido = next(m for m in matriculados if m['trip_id'] == a.id)
    assert mantido['id'] == vinculo_a['id']


async def test_subprograma_de_outra_org_nao_entra(
    client, session, token, paop
):
    alheio = await _mk_subprograma(session, uae='1gt')

    resp = await client.put(
        f'{URL}{paop["id"]}/subprogramas',
        headers=_auth(token),
        json={'subprograma_ids': [alheio.id]},
    )
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert resp.json()['message'] == 'Subprograma inexistente na organização'


@pytest.mark.parametrize(
    ('uae', 'func', 'active'),
    [
        ('1gt', 'pil', True),  # outra organização
        ('11gt', 'mc', True),  # função diferente da do subprograma
        ('11gt', 'pil', False),  # tripulante inativo
    ],
)
async def test_matricula_recusada(
    client, session, token, paop, uae, func, active
):
    sp = await _mk_subprograma(session)
    trip = await _mk_trip(session, uae=uae, func=func, active=active)

    await client.put(
        f'{URL}{paop["id"]}/subprogramas',
        headers=_auth(token),
        json={'subprograma_ids': [sp.id]},
    )
    detalhe = await client.get(f'{URL}{paop["id"]}', headers=_auth(token))
    item_id = detalhe.json()['data']['subprogramas'][0]['id']

    resp = await client.put(
        f'{URL}{paop["id"]}/subprogramas/{item_id}/tripulantes',
        headers=_auth(token),
        json={'trip_ids': [trip.id]},
    )
    assert resp.status_code == HTTPStatus.BAD_REQUEST


async def test_matriculado_que_saiu_do_criterio_nao_trava_o_item(
    client, session, token, paop
):
    """A regra vale para quem entra, não para quem já está.

    Tripulante matriculado e depois inativado continua no payload de
    reconciliação (o front pré-marca os atuais). Se a validação olhasse o
    conjunto inteiro, o item ficaria ineditável.
    """
    sp = await _mk_subprograma(session)
    veterano = await _mk_trip(session)
    novato = await _mk_trip(session)

    await client.put(
        f'{URL}{paop["id"]}/subprogramas',
        headers=_auth(token),
        json={'subprograma_ids': [sp.id]},
    )
    detalhe = await client.get(f'{URL}{paop["id"]}', headers=_auth(token))
    item_id = detalhe.json()['data']['subprogramas'][0]['id']

    await client.put(
        f'{URL}{paop["id"]}/subprogramas/{item_id}/tripulantes',
        headers=_auth(token),
        json={'trip_ids': [veterano.id]},
    )

    veterano.active = False
    session.add(veterano)
    await session.commit()

    resp = await client.put(
        f'{URL}{paop["id"]}/subprogramas/{item_id}/tripulantes',
        headers=_auth(token),
        json={'trip_ids': [veterano.id, novato.id]},
    )
    assert resp.status_code == HTTPStatus.OK

    detalhe = await client.get(f'{URL}{paop["id"]}', headers=_auth(token))
    matriculados = detalhe.json()['data']['subprogramas'][0]['tripulantes']
    assert {m['trip_id'] for m in matriculados} == {veterano.id, novato.id}


async def test_desmatricular_quem_saiu_do_criterio(
    client, session, token, paop
):
    sp = await _mk_subprograma(session)
    trip = await _mk_trip(session)

    await client.put(
        f'{URL}{paop["id"]}/subprogramas',
        headers=_auth(token),
        json={'subprograma_ids': [sp.id]},
    )
    detalhe = await client.get(f'{URL}{paop["id"]}', headers=_auth(token))
    item_id = detalhe.json()['data']['subprogramas'][0]['id']
    await client.put(
        f'{URL}{paop["id"]}/subprogramas/{item_id}/tripulantes',
        headers=_auth(token),
        json={'trip_ids': [trip.id]},
    )

    trip.func = 'mc'
    session.add(trip)
    await session.commit()

    resp = await client.put(
        f'{URL}{paop["id"]}/subprogramas/{item_id}/tripulantes',
        headers=_auth(token),
        json={'trip_ids': []},
    )
    assert resp.status_code == HTTPStatus.OK

    detalhe = await client.get(f'{URL}{paop["id"]}', headers=_auth(token))
    assert detalhe.json()['data']['subprogramas'][0]['tripulantes'] == []


async def test_remover_subprograma_com_matricula_409(
    client, session, token, paop
):
    sp = await _mk_subprograma(session)
    trip = await _mk_trip(session)

    await client.put(
        f'{URL}{paop["id"]}/subprogramas',
        headers=_auth(token),
        json={'subprograma_ids': [sp.id]},
    )
    detalhe = await client.get(f'{URL}{paop["id"]}', headers=_auth(token))
    item_id = detalhe.json()['data']['subprogramas'][0]['id']
    await client.put(
        f'{URL}{paop["id"]}/subprogramas/{item_id}/tripulantes',
        headers=_auth(token),
        json={'trip_ids': [trip.id]},
    )

    resp = await client.put(
        f'{URL}{paop["id"]}/subprogramas',
        headers=_auth(token),
        json={'subprograma_ids': []},
    )
    assert resp.status_code == HTTPStatus.CONFLICT
    assert 'SPFO-01' in resp.json()['message']


async def test_delete_paop_com_matricula_409(client, session, token, paop):
    sp = await _mk_subprograma(session)
    trip = await _mk_trip(session)

    await client.put(
        f'{URL}{paop["id"]}/subprogramas',
        headers=_auth(token),
        json={'subprograma_ids': [sp.id]},
    )
    detalhe = await client.get(f'{URL}{paop["id"]}', headers=_auth(token))
    item_id = detalhe.json()['data']['subprogramas'][0]['id']
    await client.put(
        f'{URL}{paop["id"]}/subprogramas/{item_id}/tripulantes',
        headers=_auth(token),
        json={'trip_ids': [trip.id]},
    )

    resp = await client.delete(f'{URL}{paop["id"]}', headers=_auth(token))
    assert resp.status_code == HTTPStatus.CONFLICT


async def test_delete_paop_vazio(client, token, paop):
    resp = await client.delete(f'{URL}{paop["id"]}', headers=_auth(token))
    assert resp.status_code == HTTPStatus.OK

    listagem = await client.get(URL, headers=_auth(token))
    assert listagem.json()['data'] == []


@pytest.fixture
async def paop_1gt(session):
    paop = Paop(
        uae='1gt',
        ano=2026,
        data_ini=date(2026, 1, 1),
        data_fim=date(2026, 12, 31),
        status='vigente',
    )
    session.add(paop)
    await session.commit()
    return paop


async def test_lista_nao_vaza_de_outra_org(client, token, paop_1gt):
    resp = await client.get(URL, headers=_auth(token))
    assert resp.json()['data'] == []


@pytest.mark.parametrize('metodo', ['get', 'put', 'delete'])
async def test_cross_org_404(client, token, paop_1gt, metodo):
    kwargs = {'headers': _auth(token)}
    if metodo == 'put':
        kwargs['json'] = {
            'data_ini': '2026-01-01',
            'data_fim': '2026-12-31',
            'status': 'encerrado',
        }

    resp = await getattr(client, metodo)(f'{URL}{paop_1gt.id}', **kwargs)
    assert resp.status_code == HTTPStatus.NOT_FOUND
    assert resp.json()['message'] == 'PAOP não encontrado'


async def test_set_subprogramas_cross_org_404(client, token, paop_1gt):
    resp = await client.put(
        f'{URL}{paop_1gt.id}/subprogramas',
        headers=_auth(token),
        json={'subprograma_ids': []},
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND
    assert resp.json()['message'] == 'PAOP não encontrado'


async def test_item_de_outro_paop_404(client, session, token, paop, paop_1gt):
    """item_id existente, mas pendurado noutro plano — não é do meu PAOP."""
    sp = await _mk_subprograma(session)
    await client.put(
        f'{URL}{paop["id"]}/subprogramas',
        headers=_auth(token),
        json={'subprograma_ids': [sp.id]},
    )
    detalhe = await client.get(f'{URL}{paop["id"]}', headers=_auth(token))
    item_id = detalhe.json()['data']['subprogramas'][0]['id']

    resp = await client.put(
        f'{URL}{paop_1gt.id}/subprogramas/{item_id}/tripulantes',
        headers=_auth(token),
        json={'trip_ids': []},
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.parametrize(
    ('metodo', 'sufixo'),
    [('get', ''), ('post', ''), ('put', '1'), ('delete', '1')],
)
async def test_sem_permissao_403(client, token_sem_perm, metodo, sufixo):
    kwargs = {'headers': _auth(token_sem_perm)}
    if metodo == 'post':
        kwargs['json'] = {'ano': 2026}
    if metodo == 'put':
        kwargs['json'] = {
            'data_ini': '2026-01-01',
            'data_fim': '2026-12-31',
            'status': 'rascunho',
        }

    resp = await getattr(client, metodo)(f'{URL}{sufixo}', **kwargs)
    assert resp.status_code == HTTPStatus.FORBIDDEN


async def test_sem_token_401(client):
    resp = await client.get(URL)
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


async def test_token_sistema_sem_org_400(client, token_sistema):
    """O PAOP é da unidade: sem org ativa a rota não tem o que listar."""
    resp = await client.get(URL, headers=_auth(token_sistema))
    assert resp.status_code == HTTPStatus.BAD_REQUEST
