"""
Testes para o endpoint PUT /ops/om/{id} (atualizacao de ordem).

Testa atualizacao de campos, transicao de status, geracao de numero
sequencial e substituicao de etapas.
"""

from datetime import date, datetime, timezone
from http import HTTPStatus

import pytest

from fcontrol_api.models.shared.om import Etiqueta
from tests.factories import OrdemMissaoFactory, TripFactory, UserFactory

pytestmark = pytest.mark.anyio

BASE_URL = '/ops/om'


def _make_etapa(
    dt_dep='2025-06-15T10:00:00',
    dt_arr='2025-06-15T11:30:00',
    origem='SBGL',
    dest='SBBR',
    alternativa='SBCF',
    tvoo_alt=30,
    qtd_comb=15,
    esf_aer='normal',
):
    """Helper para criar payload de etapa."""
    return {
        'dt_dep': dt_dep,
        'origem': origem,
        'dest': dest,
        'dt_arr': dt_arr,
        'alternativa': alternativa,
        'tvoo_alt': tvoo_alt,
        'qtd_comb': qtd_comb,
        'esf_aer': esf_aer,
    }


async def test_update_ordem_simple_fields(client, session, users, token):
    """Atualizacao de campos simples funciona."""
    user, _ = users

    ordem = OrdemMissaoFactory(
        created_by=user.id,
        status='rascunho',
        tipo='instrucao',
    )
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    response = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={'tipo': 'transporte', 'projeto': 'KC-390'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    data = resp['data']
    assert data['tipo'] == 'transporte'
    assert data['projeto'] == 'KC-390'


async def test_update_ordem_not_found(client, session, token):
    """Atualizacao de ordem inexistente retorna 404."""
    response = await client.put(
        f'{BASE_URL}/99999',
        json={'tipo': 'transporte'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_update_ordem_deleted_returns_404(client, session, users, token):
    """Atualizacao de ordem deletada retorna 404."""
    user, _ = users

    ordem = OrdemMissaoFactory(created_by=user.id)
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    ordem.deleted_at = datetime.now(timezone.utc)
    await session.commit()

    response = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={'tipo': 'transporte'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_update_rascunho_to_aprovada_generates_numero(
    client, session, users, token
):
    """Transicao rascunho -> aprovada gera numero sequencial."""
    user, _ = users

    ordem = OrdemMissaoFactory(
        created_by=user.id,
        status='rascunho',
        numero='auto',
        uae='11gt',
    )
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    etapa_payload = _make_etapa()

    response = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={
            'status': 'aprovada',
            'etapas': [etapa_payload],
            'esf_aer': 90,
        },
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert data['status'] == 'aprovada'
    assert data['numero'] == '001'


async def test_update_aprovada_sequential_numero(
    client, session, users, token
):
    """Segundo aprovacao no mesmo ano/UAE gera numero 002."""
    user, _ = users

    existing = OrdemMissaoFactory(
        created_by=user.id,
        status='aprovada',
        numero='001',
        uae='11gt',
        data_saida=date(2025, 6, 15),
    )
    session.add(existing)
    await session.commit()

    ordem = OrdemMissaoFactory(
        created_by=user.id,
        status='rascunho',
        numero='auto',
        uae='11gt',
    )
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    etapa_payload = _make_etapa()

    response = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={
            'status': 'aprovada',
            'etapas': [etapa_payload],
            'esf_aer': 90,
        },
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert data['numero'] == '002'


async def test_update_aprovada_requires_etapa(client, session, users, token):
    """Transicao para aprovada sem etapas falha (400)."""
    user, _ = users

    ordem = OrdemMissaoFactory(
        created_by=user.id,
        status='rascunho',
        numero='auto',
        uae='11gt',
    )
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    response = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={'status': 'aprovada'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST


async def test_update_aprovada_broken_route_continuity_fails(
    client, session, users, token
):
    """Aprovar com origem != destino da etapa anterior falha (400).

    A continuidade da rota só é exigida quando a ordem resulta
    aprovada; em rascunho a rota pode ficar incompleta.
    """
    user, _ = users

    ordem = OrdemMissaoFactory(
        created_by=user.id,
        status='rascunho',
        numero='auto',
        uae='11gt',
    )
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    etapa1 = _make_etapa(
        dt_dep='2025-06-15T10:00:00',
        dt_arr='2025-06-15T11:30:00',
        origem='SBGL',
        dest='SBBR',
    )
    # Origem SBRF != destino SBBR da etapa anterior
    etapa2 = _make_etapa(
        dt_dep='2025-06-15T14:00:00',
        dt_arr='2025-06-15T15:30:00',
        origem='SBRF',
        dest='SBCF',
    )

    response = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={
            'status': 'aprovada',
            'etapas': [etapa1, etapa2],
            'esf_aer': 180,
        },
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'origem deve ser igual ao destino' in response.json()['message']


async def test_update_replaces_etapas(client, session, users, token):
    """Atualizacao de etapas substitui todas as existentes."""
    old_etapa = _make_etapa(
        origem='SBRF',
        dest='SBSV',
    )
    create_payload = {
        'matricula_anv': '2850',
        'tipo': 'instrucao',
        'projeto': 'KC-390',
        'status': 'rascunho',
        'esf_aer': 90,
        'campos_especiais': [],
        'etapas': [old_etapa],
        'tripulacao': None,
        'etiquetas_ids': [],
    }
    create_resp = await client.post(
        f'{BASE_URL}/',
        json=create_payload,
        headers={'Authorization': f'Bearer {token}'},
    )
    assert create_resp.status_code == HTTPStatus.CREATED
    ordem_id = create_resp.json()['data']['id']

    new_etapa = _make_etapa(origem='SBGL', dest='SBBR')

    response = await client.put(
        f'{BASE_URL}/{ordem_id}',
        json={'etapas': [new_etapa]},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK

    # Verificar via GET separado (evita cache da sessao)
    get_resp = await client.get(
        f'{BASE_URL}/{ordem_id}',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert get_resp.status_code == HTTPStatus.OK
    data = get_resp.json()['data']
    assert len(data['etapas']) == 1
    assert data['etapas'][0]['origem'] == 'SBGL'
    assert data['etapas'][0]['dest'] == 'SBBR'


async def test_update_etapas_updates_data_saida(client, session, users, token):
    """Atualizacao de etapas recalcula data_saida."""
    user, _ = users

    ordem = OrdemMissaoFactory(
        created_by=user.id,
        status='rascunho',
        data_saida=date(2025, 1, 1),
    )
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    new_etapa = _make_etapa(
        dt_dep='2025-07-20T10:00:00',
        dt_arr='2025-07-20T11:30:00',
    )

    response = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={'etapas': [new_etapa], 'esf_aer': 90},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert data['data_saida'] == '2025-07-20'


async def test_update_etiquetas(client, session, users, token):
    """Atualizacao de etiquetas substitui as existentes."""
    user, _ = users

    etq1 = Etiqueta(nome='A', cor='#FF0000', uae='11gt')
    etq2 = Etiqueta(nome='B', cor='#00FF00', uae='11gt')
    session.add_all([etq1, etq2])
    await session.commit()
    await session.refresh(etq1)
    await session.refresh(etq2)

    ordem = OrdemMissaoFactory(created_by=user.id)
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    ordem.etiquetas.append(etq1)
    await session.commit()

    response = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={'etiquetas_ids': [etq2.id]},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert len(data['etiquetas']) == 1
    assert data['etiquetas'][0]['id'] == etq2.id


async def test_update_manual_numero_only_approved(
    client, session, users, token
):
    """Edicao manual de numero so permitida em ordens aprovadas."""
    user, _ = users

    ordem = OrdemMissaoFactory(
        created_by=user.id,
        status='rascunho',
        numero='auto',
    )
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    response = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={'numero': '999'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST


async def test_update_manual_numero_approved_success(
    client, session, users, token
):
    """Edicao manual de numero funciona para ordens aprovadas."""
    user, _ = users

    ordem = OrdemMissaoFactory(
        created_by=user.id,
        status='aprovada',
        numero='001',
        uae='11gt',
        data_saida=date(2025, 6, 15),
    )
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    response = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={'numero': '050'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert data['numero'] == '050'


async def test_update_manual_numero_duplicate_fails(
    client, session, users, token
):
    """Edicao manual com numero duplicado no mesmo ano/UAE falha."""
    user, _ = users

    existing = OrdemMissaoFactory(
        created_by=user.id,
        status='aprovada',
        numero='050',
        uae='11gt',
        data_saida=date(2025, 6, 15),
    )
    ordem = OrdemMissaoFactory(
        created_by=user.id,
        status='aprovada',
        numero='001',
        uae='11gt',
        data_saida=date(2025, 6, 15),
    )
    session.add_all([existing, ordem])
    await session.commit()
    await session.refresh(ordem)

    response = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={'numero': '050'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST


async def test_update_status_requires_status_permission(
    client, session, users, om_editor_token
):
    """Transitar status sem `ordem_missao.status.update` retorna 403.

    `om_editor_token` tem `ordem_missao.update` (edita campos) mas não a
    permissão granular de status. O payload aprovaria a OM se o gate não
    existisse (etapa válida + transição válida), então o 403 isola a
    permissão granular, não uma falha de validação.
    """
    user, _ = users

    ordem = OrdemMissaoFactory(
        created_by=user.id,
        status='rascunho',
        numero='auto',
        uae='11gt',
    )
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    response = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={
            'status': 'aprovada',
            'etapas': [_make_etapa()],
            'esf_aer': 90,
        },
        headers={'Authorization': f'Bearer {om_editor_token}'},
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert 'ordem_missao.status.update' in response.json()['message']


async def test_update_fields_without_status_permission_ok(
    client, session, users, om_editor_token
):
    """Editar campos (sem trocar status) só exige `ordem_missao.update`."""
    user, _ = users

    ordem = OrdemMissaoFactory(
        created_by=user.id,
        status='rascunho',
        tipo='instrucao',
        uae='11gt',
    )
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    response = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={'tipo': 'transporte'},
        headers={'Authorization': f'Bearer {om_editor_token}'},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['data']['tipo'] == 'transporte'


async def test_update_ordem_requires_auth(client):
    """Endpoint requer autenticacao."""
    response = await client.put(f'{BASE_URL}/1', json={'tipo': 'transporte'})
    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_update_preserva_p_g_snapshot_da_tripulacao(
    client, session, users, token
):
    """Editar a OM nao recarimba o posto de quem ja estava nela.

    `p_g` e snapshot do posto na criacao da ordem. O update apaga e
    recria a tripulacao; sem preservar o valor gravado, promover um
    militar em 2026 reescreveria a OM de 2024 na primeira edicao —
    mesmo numa edicao que so troca a data.
    """
    user, _ = users

    antigo = UserFactory(p_g='cb')
    novato = UserFactory(p_g='3s')
    session.add_all([antigo, novato])
    await session.flush()

    trip_antigo = TripFactory(user_id=antigo.id)
    trip_novato = TripFactory(user_id=novato.id)
    session.add_all([trip_antigo, trip_novato])
    await session.commit()
    await session.refresh(trip_antigo)
    await session.refresh(trip_novato)

    create_resp = await client.post(
        f'{BASE_URL}/',
        json={
            'matricula_anv': '2850',
            'tipo': 'instrucao',
            'projeto': 'KC-390',
            'status': 'rascunho',
            'esf_aer': 90,
            'campos_especiais': [],
            'etapas': [_make_etapa()],
            'tripulacao': {'pil': [trip_antigo.id]},
            'etiquetas_ids': [],
        },
        headers={'Authorization': f'Bearer {token}'},
    )
    assert create_resp.status_code == HTTPStatus.CREATED
    ordem_id = create_resp.json()['data']['id']

    # A OM nasce com o posto vigente na criacao.
    criada = create_resp.json()['data']['tripulacao']
    assert [t['p_g'] for t in criada] == ['cb']

    # Promocao posterior: o militar vira '2s' depois da OM criada.
    antigo.p_g = '2s'
    session.add(antigo)
    await session.commit()

    # Edicao qualquer da OM, reenviando a tripulacao (agora com +1).
    update_resp = await client.put(
        f'{BASE_URL}/{ordem_id}',
        json={'tripulacao': {'pil': [trip_antigo.id, trip_novato.id]}},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert update_resp.status_code == HTTPStatus.OK

    get_resp = await client.get(
        f'{BASE_URL}/{ordem_id}',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert get_resp.status_code == HTTPStatus.OK
    por_trip = {
        t['tripulante_id']: t['p_g']
        for t in get_resp.json()['data']['tripulacao']
    }

    # Quem ja estava mantem o snapshot; o novato entra com o posto atual.
    assert por_trip[trip_antigo.id] == 'cb'
    assert por_trip[trip_novato.id] == '3s'


async def test_update_remove_e_readiciona_tripulante_usa_posto_atual(
    client, session, users, token
):
    """Tripulante que sai da OM e volta depois entra como novo.

    O mapa preservado vem das linhas vivas da ordem. Quem nao esta mais
    nela no momento da edicao nao tem snapshot a preservar, e portanto e
    carimbado com o posto atual — o mesmo que aconteceria ao adiciona-lo
    pela primeira vez.
    """
    user, _ = users

    militar = UserFactory(p_g='cb')
    session.add(militar)
    await session.flush()

    trip = TripFactory(user_id=militar.id)
    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    create_resp = await client.post(
        f'{BASE_URL}/',
        json={
            'matricula_anv': '2850',
            'tipo': 'instrucao',
            'projeto': 'KC-390',
            'status': 'rascunho',
            'esf_aer': 90,
            'campos_especiais': [],
            'etapas': [_make_etapa()],
            'tripulacao': {'pil': [trip.id]},
            'etiquetas_ids': [],
        },
        headers={'Authorization': f'Bearer {token}'},
    )
    assert create_resp.status_code == HTTPStatus.CREATED
    ordem_id = create_resp.json()['data']['id']

    # Sai da ordem.
    remove_resp = await client.put(
        f'{BASE_URL}/{ordem_id}',
        json={'tripulacao': {'pil': []}},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert remove_resp.status_code == HTTPStatus.OK

    militar.p_g = '2s'
    session.add(militar)
    await session.commit()

    # Volta para a ordem ja promovido.
    volta_resp = await client.put(
        f'{BASE_URL}/{ordem_id}',
        json={'tripulacao': {'pil': [trip.id]}},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert volta_resp.status_code == HTTPStatus.OK

    get_resp = await client.get(
        f'{BASE_URL}/{ordem_id}',
        headers={'Authorization': f'Bearer {token}'},
    )
    tripulacao = get_resp.json()['data']['tripulacao']
    assert len(tripulacao) == 1
    assert tripulacao[0]['p_g'] == '2s'


async def test_update_troca_de_funcao_usa_posto_atual(
    client, session, users, token
):
    """Trocar a funcao do tripulante recarimba o posto — por contrato.

    A identidade da linha em `om_tripulacao` e o par
    (tripulante_id, funcao): nao ha outra coluna estavel. Uma linha
    (fulano, mc) que nunca existiu nao tem snapshot a preservar, e
    herda-lo de (fulano, pil) seria adivinhacao — erraria no caso
    legitimo em que a OM ganha um `mc` novo enquanto o `pil` sai.
    O historico fino da linha antiga continua no `log_user_action`.

    Este teste congela a decisao: se alguem casar so por `tripulante_id`,
    ele fica vermelho e a discussao reabre com dado.
    """
    user, _ = users

    militar = UserFactory(p_g='cb')
    session.add(militar)
    await session.flush()

    trip = TripFactory(user_id=militar.id)
    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    create_resp = await client.post(
        f'{BASE_URL}/',
        json={
            'matricula_anv': '2850',
            'tipo': 'instrucao',
            'projeto': 'KC-390',
            'status': 'rascunho',
            'esf_aer': 90,
            'campos_especiais': [],
            'etapas': [_make_etapa()],
            'tripulacao': {'pil': [trip.id]},
            'etiquetas_ids': [],
        },
        headers={'Authorization': f'Bearer {token}'},
    )
    assert create_resp.status_code == HTTPStatus.CREATED
    ordem_id = create_resp.json()['data']['id']

    militar.p_g = '2s'
    session.add(militar)
    await session.commit()

    # Mesmo militar, funcao diferente: linha nova, sem snapshot.
    update_resp = await client.put(
        f'{BASE_URL}/{ordem_id}',
        json={'tripulacao': {'mc': [trip.id]}},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert update_resp.status_code == HTTPStatus.OK

    get_resp = await client.get(
        f'{BASE_URL}/{ordem_id}',
        headers={'Authorization': f'Bearer {token}'},
    )
    tripulacao = get_resp.json()['data']['tripulacao']
    assert len(tripulacao) == 1
    assert tripulacao[0]['funcao'] == 'mc'
    assert tripulacao[0]['p_g'] == '2s'


async def test_update_sem_tripulacao_no_payload_preserva_snapshot(
    client, session, users, token
):
    """Editar so a data nao toca a tripulacao nem o snapshot.

    Cobre o ramo `tripulacao_no_payload is False`: sem a chave no PUT,
    as linhas originais nao sao apagadas nem recriadas. E o cenario que
    originou a correcao — a edicao inocua de uma OM antiga.
    """
    user, _ = users

    militar = UserFactory(p_g='cb')
    session.add(militar)
    await session.flush()

    trip = TripFactory(user_id=militar.id)
    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    create_resp = await client.post(
        f'{BASE_URL}/',
        json={
            'matricula_anv': '2850',
            'tipo': 'instrucao',
            'projeto': 'KC-390',
            'status': 'rascunho',
            'esf_aer': 90,
            'campos_especiais': [],
            'etapas': [_make_etapa()],
            'tripulacao': {'pil': [trip.id]},
            'etiquetas_ids': [],
        },
        headers={'Authorization': f'Bearer {token}'},
    )
    assert create_resp.status_code == HTTPStatus.CREATED
    ordem_id = create_resp.json()['data']['id']

    militar.p_g = '2s'
    session.add(militar)
    await session.commit()

    # PUT sem a chave `tripulacao`.
    update_resp = await client.put(
        f'{BASE_URL}/{ordem_id}',
        json={'tipo': 'transporte'},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert update_resp.status_code == HTTPStatus.OK

    get_resp = await client.get(
        f'{BASE_URL}/{ordem_id}',
        headers={'Authorization': f'Bearer {token}'},
    )
    data = get_resp.json()['data']
    assert data['tipo'] == 'transporte'
    assert len(data['tripulacao']) == 1
    assert data['tripulacao'][0]['p_g'] == 'cb'


async def test_update_aceita_funcao_do_catalogo_da_unidade(
    client, session, users, token
):
    """Funcao fora do conjunto fixo antigo (`md`) e gravada, nao descartada.

    A lista de funcoes e dado, nao codigo. Antes, um schema de chaves
    fixas descartava `md`/`ml` em silencio: o POST respondia 201 e o
    medico simplesmente nao existia na OM.
    """
    user, _ = users

    militar = UserFactory(p_g='cb')
    session.add(militar)
    await session.flush()

    trip = TripFactory(user_id=militar.id)
    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    create_resp = await client.post(
        f'{BASE_URL}/',
        json={
            'matricula_anv': '2850',
            'tipo': 'instrucao',
            'projeto': 'KC-390',
            'status': 'rascunho',
            'esf_aer': 90,
            'campos_especiais': [],
            'etapas': [_make_etapa()],
            'tripulacao': {'md': [trip.id]},
            'etiquetas_ids': [],
        },
        headers={'Authorization': f'Bearer {token}'},
    )
    assert create_resp.status_code == HTTPStatus.CREATED

    tripulacao = create_resp.json()['data']['tripulacao']
    assert len(tripulacao) == 1
    assert tripulacao[0]['funcao'] == 'md'


async def test_update_funcao_nao_operada_pela_unidade_400(
    client, session, users, token
):
    """Funcao fora do catalogo da unidade falha alto, sem perda silenciosa."""
    user, _ = users

    militar = UserFactory(p_g='cb')
    session.add(militar)
    await session.flush()

    trip = TripFactory(user_id=militar.id)
    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    ordem = OrdemMissaoFactory(created_by=user.id, uae='11gt')
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    resp = await client.put(
        f'{BASE_URL}/{ordem.id}',
        json={'tripulacao': {'xx': [trip.id]}},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert 'xx' in resp.json()['message']
