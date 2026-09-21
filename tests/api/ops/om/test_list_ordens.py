"""
Testes para o endpoint GET /ops/om/ (listagem de ordens de missao).

Testa paginacao, filtros por status, datas, busca textual e etiquetas.
"""

from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus

import pytest

from fcontrol_api.models.shared.om import Etiqueta
from tests.factories import OrdemEtapaFactory, OrdemMissaoFactory

pytestmark = pytest.mark.anyio

BASE_URL = '/ops/om/'


async def test_list_ordens_empty(client, session, token):
    """Listagem sem ordens retorna lista vazia."""
    response = await client.get(
        BASE_URL,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['data'] == []
    assert resp['total'] == 0
    assert resp['page'] == 1


async def test_list_ordens_returns_items(client, session, users, token):
    """Listagem retorna ordens existentes."""
    user, _ = users

    ordem = OrdemMissaoFactory(created_by=user.id)
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    response = await client.get(
        BASE_URL,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert resp['total'] == 1
    assert len(resp['data']) == 1
    assert resp['data'][0]['id'] == ordem.id


async def test_list_ordens_excludes_deleted(client, session, users, token):
    """Ordens deletadas (soft delete) nao aparecem na listagem."""
    user, _ = users

    ordem = OrdemMissaoFactory(created_by=user.id)
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    ordem.deleted_at = datetime.now(timezone.utc)
    await session.commit()

    response = await client.get(
        BASE_URL,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] == 0
    assert resp['data'] == []


async def test_list_ordens_pagination(client, session, users, token):
    """Paginacao retorna itens corretos por pagina."""
    user, _ = users

    for _ in range(5):
        session.add(OrdemMissaoFactory(created_by=user.id))
    await session.commit()

    response = await client.get(
        BASE_URL,
        params={'page': 1, 'per_page': 2},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] == 5
    assert len(resp['data']) == 2
    assert resp['page'] == 1
    assert resp['per_page'] == 2
    assert resp['pages'] == 3


async def test_list_ordens_pagination_last_page(client, session, users, token):
    """Ultima pagina retorna itens restantes."""
    user, _ = users

    for _ in range(5):
        session.add(OrdemMissaoFactory(created_by=user.id))
    await session.commit()

    response = await client.get(
        BASE_URL,
        params={'page': 3, 'per_page': 2},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] == 5
    assert len(resp['data']) == 1
    assert resp['page'] == 3


async def test_list_ordens_filter_status(client, session, users, token):
    """Filtro por status retorna apenas ordens com status especifico."""
    user, _ = users

    session.add(OrdemMissaoFactory(created_by=user.id, status='rascunho'))
    session.add(OrdemMissaoFactory(created_by=user.id, status='aprovada'))
    session.add(OrdemMissaoFactory(created_by=user.id, status='aprovada'))
    await session.commit()

    response = await client.get(
        BASE_URL,
        params={'status': 'aprovada'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] == 2
    for item in resp['data']:
        assert item['status'] == 'aprovada'


async def test_list_ordens_filter_multiple_status(
    client, session, users, token
):
    """Filtro com multiplos status retorna ordens de ambos."""
    user, _ = users

    session.add(OrdemMissaoFactory(created_by=user.id, status='rascunho'))
    session.add(OrdemMissaoFactory(created_by=user.id, status='aprovada'))
    session.add(OrdemMissaoFactory(created_by=user.id, status='cancelada'))
    await session.commit()

    response = await client.get(
        BASE_URL,
        params=[
            ('status', 'rascunho'),
            ('status', 'aprovada'),
        ],
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] == 2


async def test_list_ordens_filter_status_ne(client, session, users, token):
    """Filtro status_ne exclui ordens com status especifico."""
    user, _ = users

    session.add(OrdemMissaoFactory(created_by=user.id, status='rascunho'))
    session.add(OrdemMissaoFactory(created_by=user.id, status='aprovada'))
    await session.commit()

    response = await client.get(
        BASE_URL,
        params={'status_ne': 'rascunho'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] == 1
    assert resp['data'][0]['status'] == 'aprovada'


async def test_list_ordens_filter_data_inicio_fim(
    client, session, users, token
):
    """Filtro por data_inicio e data_fim retorna ordens no intervalo."""
    user, _ = users

    today = date.today()
    ordem_hoje = OrdemMissaoFactory(created_by=user.id, data_saida=today)
    ordem_passado = OrdemMissaoFactory(
        created_by=user.id,
        data_saida=today - timedelta(days=30),
    )
    session.add_all([ordem_hoje, ordem_passado])
    await session.commit()
    await session.refresh(ordem_hoje)
    await session.refresh(ordem_passado)

    # O filtro de data do router opera sobre dt_dep das etapas, não sobre
    # data_saida; criamos etapas coerentes para cada ordem.
    now = datetime.now(timezone.utc)
    session.add_all([
        OrdemEtapaFactory(ordem_id=ordem_hoje.id, dt_dep=now),
        OrdemEtapaFactory(
            ordem_id=ordem_passado.id, dt_dep=now - timedelta(days=30)
        ),
    ])
    await session.commit()

    response = await client.get(
        BASE_URL,
        params={
            'data_inicio': (today - timedelta(days=1)).isoformat(),
            'data_fim': (today + timedelta(days=1)).isoformat(),
        },
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] == 1


async def test_list_ordens_busca_by_numero(client, session, users, token):
    """Busca por numero da ordem retorna resultado correto."""
    user, _ = users

    ordem = OrdemMissaoFactory(created_by=user.id, numero='OM-UNICO-123')
    session.add(ordem)
    session.add(OrdemMissaoFactory(created_by=user.id))
    await session.commit()

    response = await client.get(
        BASE_URL,
        params={'busca': 'UNICO'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] == 1
    assert resp['data'][0]['numero'] == 'OM-UNICO-123'


async def test_list_ordens_busca_by_tipo(client, session, users, token):
    """Busca por tipo da ordem retorna resultado correto."""
    user, _ = users

    ordem = OrdemMissaoFactory(created_by=user.id, tipo='instrucao')
    session.add(ordem)
    session.add(OrdemMissaoFactory(created_by=user.id, tipo='transporte'))
    await session.commit()

    response = await client.get(
        BASE_URL,
        params={'busca': 'instrucao'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] == 1
    assert resp['data'][0]['tipo'] == 'instrucao'


async def test_list_ordens_busca_by_icao(client, session, users, token):
    """Busca por codigo ICAO de etapa retorna a ordem."""
    user, _ = users

    ordem = OrdemMissaoFactory(created_by=user.id)
    session.add(ordem)
    await session.commit()
    await session.refresh(ordem)

    etapa = OrdemEtapaFactory(ordem_id=ordem.id, origem='SBGL', dest='SBBR')
    session.add(etapa)
    await session.commit()

    response = await client.get(
        BASE_URL,
        params={'busca': 'SBGL'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] >= 1
    ids = [item['id'] for item in resp['data']]
    assert ordem.id in ids


async def test_list_ordens_filter_etiquetas(client, session, users, token):
    """Filtro por etiquetas retorna ordens vinculadas."""
    user, _ = users

    etiqueta = Etiqueta(
        nome='Urgente', cor='#FF0000', descricao='Teste', uae='11gt'
    )
    session.add(etiqueta)
    await session.commit()
    await session.refresh(etiqueta)

    ordem_com = OrdemMissaoFactory(created_by=user.id)
    ordem_sem = OrdemMissaoFactory(created_by=user.id)
    session.add_all([ordem_com, ordem_sem])
    await session.commit()
    await session.refresh(ordem_com)
    await session.refresh(ordem_sem)

    ordem_com.etiquetas.append(etiqueta)
    await session.commit()

    response = await client.get(
        BASE_URL,
        params={'etiquetas_ids': etiqueta.id},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] == 1
    assert resp['data'][0]['id'] == ordem_com.id


async def test_list_ordens_read_without_write_permission(
    client, session, users, token_sem_perm
):
    """Leitura exige apenas org ativa, nao permissao de escrita.

    `token_sem_perm` nao tem grant ordem_missao na org ativa, mas a listagem
    e uma rota de leitura (so ActiveOrg) e deve responder 200.
    """
    user, _ = users
    session.add(OrdemMissaoFactory(created_by=user.id))
    await session.commit()

    response = await client.get(
        BASE_URL,
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['total'] == 1


async def test_list_ordens_missing_active_org_fails(client, token_sistema):
    """Sem org ativa no token_sistema, listar ordens responde 400."""
    response = await client.get(
        BASE_URL,
        headers={'Authorization': f'Bearer {token_sistema}'},
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST


async def test_list_ordens_requires_auth(client):
    """Endpoint requer autenticacao."""
    response = await client.get(BASE_URL)
    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_list_ordens_filtro_data_usa_dia_utc(
    client, session, users, token
):
    """Filtro de data recorta pelo dia UTC da decolagem.

    Etapas perto da meia-noite sao o caso que denuncia conversao de fuso:
    23:30Z e 01:00Z do dia seguinte pertencem a dias UTC diferentes. Como o
    horario da OM e Zulu ponta a ponta (o quadro desenha a etapa no dia que
    vem na string ISO), o recorte tem de concordar com esse dia
    independentemente do TimeZone do servidor Postgres.
    """
    user, _ = users
    dia = date(2026, 3, 11)

    ordem_23h30 = OrdemMissaoFactory(created_by=user.id, data_saida=dia)
    ordem_01h = OrdemMissaoFactory(created_by=user.id, data_saida=dia)
    session.add_all([ordem_23h30, ordem_01h])
    await session.commit()
    await session.refresh(ordem_23h30)
    await session.refresh(ordem_01h)

    session.add_all([
        OrdemEtapaFactory(
            ordem_id=ordem_23h30.id,
            dt_dep=datetime(2026, 3, 11, 23, 30, tzinfo=timezone.utc),
        ),
        OrdemEtapaFactory(
            ordem_id=ordem_01h.id,
            dt_dep=datetime(2026, 3, 12, 1, 0, tzinfo=timezone.utc),
        ),
    ])
    await session.commit()

    # Janela de um unico dia UTC: so a etapa das 23:30Z entra.
    response = await client.get(
        BASE_URL,
        params={'data_inicio': '2026-03-11', 'data_fim': '2026-03-11'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['total'] == 1
    assert resp['data'][0]['id'] == ordem_23h30.id

    # O dia seguinte pega a outra, confirmando que a borda separa as duas.
    response = await client.get(
        BASE_URL,
        params={'data_inicio': '2026-03-12', 'data_fim': '2026-03-12'},
        headers={'Authorization': f'Bearer {token}'},
    )

    resp = response.json()
    assert resp['total'] == 1
    assert resp['data'][0]['id'] == ordem_01h.id


async def test_list_ordens_ordem_cronologica_por_decolagem(
    client, session, users, token
):
    """`ordem=cronologica` devolve a janela por data de decolagem.

    Sem isso o corte do `per_page` guardaria as OMs cadastradas por ultimo
    em vez das do inicio da janela — missao dentro do periodo sumiria do
    quadro de operacoes.
    """
    user, _ = users
    dia = date(2026, 4, 6)

    # Cadastradas na ordem inversa da cronologica de propósito.
    ordem_tarde = OrdemMissaoFactory(created_by=user.id, data_saida=dia)
    session.add(ordem_tarde)
    await session.commit()
    await session.refresh(ordem_tarde)

    ordem_cedo = OrdemMissaoFactory(created_by=user.id, data_saida=dia)
    session.add(ordem_cedo)
    await session.commit()
    await session.refresh(ordem_cedo)

    session.add_all([
        OrdemEtapaFactory(
            ordem_id=ordem_tarde.id,
            dt_dep=datetime(2026, 4, 6, 18, 0, tzinfo=timezone.utc),
        ),
        OrdemEtapaFactory(
            ordem_id=ordem_cedo.id,
            dt_dep=datetime(2026, 4, 6, 6, 0, tzinfo=timezone.utc),
        ),
    ])
    await session.commit()

    response = await client.get(
        BASE_URL,
        params={
            'data_inicio': '2026-04-06',
            'data_fim': '2026-04-06',
            'ordem': 'cronologica',
        },
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    ids = [item['id'] for item in response.json()['data']]
    assert ids == [ordem_cedo.id, ordem_tarde.id]

    # Sem pedir `cronologica`, o filtro de data NÃO pode inverter a ordem
    # da listagem: as mais recentes por cadastro vêm primeiro. A tela
    # `/ops/om` filtra por período e quebrou quando isso era implícito.
    response = await client.get(
        BASE_URL,
        params={'data_inicio': '2026-04-06', 'data_fim': '2026-04-06'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    ids = [item['id'] for item in response.json()['data']]
    # `ordem_cedo` foi cadastrada por último, então vem primeiro — ordem de
    # cadastro, e não a cronológica das etapas.
    assert ids == [ordem_cedo.id, ordem_tarde.id]


async def test_list_ordens_ordem_numerica_por_ano_e_numero(
    client, session, users, token
):
    """`ordem=numerica` devolve ano da OM e numeração, decrescente.

    É como a OM é identificada (o par único por UAE). Ordenar no cliente
    acertaria a ordem dentro da página e erraria quais OMs caem em cada
    uma, porque o corte do `per_page` acontece aqui.
    """
    user, _ = users

    # Cadastradas embaralhadas de propósito: a ordem de cadastro não pode
    # sobreviver ao `ordem=numerica`.
    esperado = [
        ('2026', '002'),
        ('2026', '001'),
        ('2025', '010'),
    ]
    criadas = {}
    for ano, numero in [('2025', '010'), ('2026', '002'), ('2026', '001')]:
        om = OrdemMissaoFactory(
            created_by=user.id,
            numero=numero,
            data_saida=date(int(ano), 5, 20),
        )
        session.add(om)
        await session.commit()
        await session.refresh(om)
        criadas[(ano, numero)] = om.id

    response = await client.get(
        BASE_URL,
        params={'ordem': 'numerica'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    ids = [item['id'] for item in response.json()['data']]
    assert ids == [criadas[chave] for chave in esperado]


async def test_list_ordens_ordem_numerica_compara_numero_como_inteiro(
    client, session, users, token
):
    """A numeração compara como inteiro, não como texto.

    `numero` é String: por texto '1000' viria antes de '999' assim que a
    numeração passar de três dígitos.
    """
    user, _ = users
    ano = date(2026, 6, 10)

    om_999 = OrdemMissaoFactory(
        created_by=user.id, numero='999', data_saida=ano
    )
    session.add(om_999)
    await session.commit()
    await session.refresh(om_999)

    om_1000 = OrdemMissaoFactory(
        created_by=user.id, numero='1000', data_saida=ano
    )
    session.add(om_1000)
    await session.commit()
    await session.refresh(om_1000)

    response = await client.get(
        BASE_URL,
        params={'ordem': 'numerica'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    ids = [item['id'] for item in response.json()['data']]
    assert ids == [om_1000.id, om_999.id]


async def test_list_ordens_ordem_numerica_incompletas_no_topo(
    client, session, users, token
):
    """Sem ano ou sem número utilizável, a OM sobe ao topo.

    Cadastro incompleto precisa de atenção; escondê-lo no fim da última
    página é o mesmo que perdê-lo. Cobre `data_saida` nula e `numero`
    não-numérico, que o cast para Integer não pode tocar.
    """
    user, _ = users

    om_numerada = OrdemMissaoFactory(
        created_by=user.id, numero='005', data_saida=date(2026, 7, 1)
    )
    session.add(om_numerada)
    await session.commit()
    await session.refresh(om_numerada)

    om_sem_numero = OrdemMissaoFactory(
        created_by=user.id, numero='auto', data_saida=date(2026, 7, 1)
    )
    session.add(om_sem_numero)
    await session.commit()
    await session.refresh(om_sem_numero)

    om_sem_ano = OrdemMissaoFactory(
        created_by=user.id, numero='007', data_saida=None
    )
    session.add(om_sem_ano)
    await session.commit()
    await session.refresh(om_sem_ano)

    response = await client.get(
        BASE_URL,
        params={'ordem': 'numerica'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    ids = [item['id'] for item in response.json()['data']]
    # Sem ano vem antes de tudo; dentro de 2026, a sem número antes da
    # numerada.
    assert ids == [om_sem_ano.id, om_sem_numero.id, om_numerada.id]


@pytest.mark.parametrize(
    'params',
    [
        {'per_page': 5000},  # acima do teto: varreria a tabela inteira
        {'per_page': 0},  # sem piso, estourava ZeroDivisionError (500)
        {'per_page': -5},  # LIMIT negativo no Postgres
        {'page': 0},
    ],
)
async def test_list_ordens_paginacao_fora_da_faixa_e_422(
    client, session, users, token, params
):
    """Paginação fora da faixa é recusada, não corrigida em silêncio.

    O limite vive na assinatura (`Query(ge=..., le=...)`), então o cliente
    recebe 422 e descobre o que errou, em vez de um 200 com outro valor.
    `per_page=0` chegava a `paginated_response` e derrubava o cálculo de
    `pages` com ZeroDivisionError — um 500.
    """
    user, _ = users
    session.add(OrdemMissaoFactory(created_by=user.id))
    await session.commit()

    response = await client.get(
        BASE_URL,
        params=params,
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
