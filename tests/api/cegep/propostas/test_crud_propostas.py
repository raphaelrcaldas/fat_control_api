"""CRUD das propostas de comissionamento (/cegep/propostas).

A proposta é uma simulação: hierarquia Proposta → Cenários → Linhas, gravada
de uma vez pelo PUT (o front edita um rascunho local). Os dois pontos que
sustentam a tela e por isso viram teste:

- **o GET devolve `linha.user`** — o payload de escrita só manda `user_id`, e
  sem o join a tela perde o nome de todos os militares depois de salvar;
- **o PUT preserva os ids** — é pelo eco deles que o rascunho para de tratar
  registro existente como novo a cada save.
"""

from http import HTTPStatus

import pytest

from tests.api.cegep.propostas.conftest import (
    URL,
    auth,
    linha,
    payload_com_linhas,
)
from tests.factories import UserFactory

pytestmark = pytest.mark.anyio


async def test_create_nasce_com_cenario(client, token):
    """O sandbox sempre tem um cenário ativo — o front assume >= 1."""
    resp = await client.post(
        URL, json={'nome': 'Proposta X', 'ano_ref': 2026}, headers=auth(token)
    )

    assert resp.status_code == HTTPStatus.CREATED
    data = resp.json()['data']
    assert data['status'] == 'rascunho'
    assert len(data['cenarios']) == 1
    assert data['cenarios'][0]['cor'] == 'sky'
    assert data['cenarios'][0]['linhas'] == []


async def test_get_devolve_militar_da_linha(
    client, token, proposta, militar_11gt
):
    """Sem este join a tela perde o nome de todos os militares ao salvar."""
    await client.put(
        f'{URL}{proposta["id"]}',
        json=payload_com_linhas(proposta, [linha(militar_11gt.id)]),
        headers=auth(token),
    )

    resp = await client.get(f'{URL}{proposta["id"]}', headers=auth(token))

    assert resp.status_code == HTTPStatus.OK
    linha_out = resp.json()['data']['cenarios'][0]['linhas'][0]
    assert linha_out['user']['id'] == militar_11gt.id
    assert linha_out['user']['nome_guerra'] == militar_11gt.nome_guerra
    # Dinheiro sai como float no JSON, apesar de Numeric no banco.
    assert isinstance(linha_out['base_ab'], float)


async def test_put_preserva_ids_e_sincroniza(
    client, token, proposta, militar_11gt, session
):
    """Salvar duas vezes não pode recriar cenário nem linha."""
    outro = UserFactory(unidade='11gt')
    session.add(outro)
    await session.commit()

    primeiro = await client.put(
        f'{URL}{proposta["id"]}',
        json=payload_com_linhas(
            proposta,
            [linha(militar_11gt.id), linha(outro.id)],
            cenarios_extras=[
                {'nome': 'Ampliado', 'cor': 'violet', 'linhas': []}
            ],
        ),
        headers=auth(token),
    )
    assert primeiro.status_code == HTTPStatus.OK
    antes = primeiro.json()['data']
    ids_cenarios = [c['id'] for c in antes['cenarios']]
    ids_linhas = [linha_['id'] for linha_ in antes['cenarios'][0]['linhas']]
    assert len(ids_cenarios) == 2

    # Segundo save: devolve os ids ecoados e remove uma linha e um cenário.
    segundo = await client.put(
        f'{URL}{proposta["id"]}',
        json={
            'nome': 'Renomeada',
            'ano_ref': 2026,
            'cenarios': [
                {
                    'id': ids_cenarios[0],
                    'nome': antes['cenarios'][0]['nome'],
                    'cor': 'emerald',
                    'linhas': [
                        linha(militar_11gt.id, id=ids_linhas[0], base=2500.0)
                    ],
                }
            ],
        },
        headers=auth(token),
    )

    assert segundo.status_code == HTTPStatus.OK
    depois = segundo.json()['data']
    assert depois['nome'] == 'Renomeada'
    assert [c['id'] for c in depois['cenarios']] == [ids_cenarios[0]]
    assert depois['cenarios'][0]['cor'] == 'emerald'
    linhas = depois['cenarios'][0]['linhas']
    assert [linha_['id'] for linha_ in linhas] == [ids_linhas[0]]
    assert linhas[0]['base_ab'] == 2500.0


async def test_remover_cenario_do_meio(client, token, proposta):
    """Sair do meio renumera a `ordem` dos seguintes.

    O unit of work emite INSERT/UPDATE antes de DELETE no mesmo mapper: o
    cenário C recebia `ordem=1` enquanto o B, ainda vivo, ocupava o mesmo
    valor. Só não estoura porque o UNIQUE é DEFERRABLE INITIALLY DEFERRED.
    """
    extras = [
        {'nome': 'Cenário B', 'cor': 'violet', 'linhas': []},
        {'nome': 'Cenário C', 'cor': 'emerald', 'linhas': []},
    ]
    criados = await client.put(
        f'{URL}{proposta["id"]}',
        json=payload_com_linhas(proposta, [], cenarios_extras=extras),
        headers=auth(token),
    )
    cenarios = criados.json()['data']['cenarios']
    assert [c['nome'] for c in cenarios] == [
        'Cenário A',
        'Cenário B',
        'Cenário C',
    ]

    sem_o_meio = await client.put(
        f'{URL}{proposta["id"]}',
        json={
            'nome': proposta['nome'],
            'ano_ref': proposta['ano_ref'],
            'cenarios': [
                {**c, 'linhas': []} for c in (cenarios[0], cenarios[2])
            ],
        },
        headers=auth(token),
    )

    assert sem_o_meio.status_code == HTTPStatus.OK
    restantes = sem_o_meio.json()['data']['cenarios']
    assert [c['id'] for c in restantes] == [
        cenarios[0]['id'],
        cenarios[2]['id'],
    ]


async def test_militar_removido_e_readicionado_no_mesmo_save(
    client, token, proposta, militar_11gt
):
    """Remover e recolocar o militar antes de salvar perde o id da linha.

    A linha volta como nova, então o mesmo `(cenario_id, user_id)` é inserido
    antes de a linha antiga ser apagada — de novo, só passa porque o UNIQUE
    é DEFERRABLE.
    """
    antes = await client.put(
        f'{URL}{proposta["id"]}',
        json=payload_com_linhas(proposta, [linha(militar_11gt.id)]),
        headers=auth(token),
    )
    id_antigo = antes.json()['data']['cenarios'][0]['linhas'][0]['id']

    # Sem `id`: é o que o rascunho manda depois do toggle remove + adiciona.
    depois = await client.put(
        f'{URL}{proposta["id"]}',
        json=payload_com_linhas(
            proposta, [linha(militar_11gt.id, base=3000.0)]
        ),
        headers=auth(token),
    )

    assert depois.status_code == HTTPStatus.OK
    linhas = depois.json()['data']['cenarios'][0]['linhas']
    assert len(linhas) == 1
    assert linhas[0]['id'] != id_antigo
    assert linhas[0]['base_ab'] == 3000.0


async def test_updated_at_avanca_quando_so_as_linhas_mudam(
    client, token, proposta, militar_11gt
):
    """A lista ordena por `updated_at` — ele não pode congelar.

    O `onupdate` do model não dispara quando nenhuma coluna de `propostas`
    muda, e o trabalho de verdade acontece nos cenários.
    """
    resp = await client.put(
        f'{URL}{proposta["id"]}',
        json=payload_com_linhas(proposta, [linha(militar_11gt.id)]),
        headers=auth(token),
    )

    assert resp.json()['data']['updated_at'] > proposta['updated_at']


async def test_base_com_digitos_demais_reprova(
    client, token, proposta, militar_11gt
):
    """`Numeric(14, 2)` estoura como 500; o schema tem de barrar antes."""
    corpo = payload_com_linhas(proposta, [linha(militar_11gt.id)])
    corpo['cenarios'][0]['linhas'][0]['base_ab'] = 10**15

    resp = await client.put(
        f'{URL}{proposta["id"]}', json=corpo, headers=auth(token)
    )

    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_lista_filtra_por_exercicio(client, token, proposta):
    """A aba abre no exercício corrente e filtra por ele."""
    await client.post(
        URL, json={'nome': 'De 2027', 'ano_ref': 2027}, headers=auth(token)
    )

    de_2026 = await client.get(f'{URL}?ano_ref=2026', headers=auth(token))
    de_2027 = await client.get(f'{URL}?ano_ref=2027', headers=auth(token))
    todas = await client.get(URL, headers=auth(token))

    anos_2026 = {p['ano_ref'] for p in de_2026.json()['data']}
    anos_2027 = {p['ano_ref'] for p in de_2027.json()['data']}
    assert anos_2026 == {2026}
    assert anos_2027 == {2027}
    assert len(todas.json()['data']) >= 2
    # `cenarios_count` sem carregar os cenários.
    assert all('cenarios_count' in p for p in todas.json()['data'])


async def test_delete_leva_cenarios_e_linhas(
    client, token, proposta, militar_11gt
):
    await client.put(
        f'{URL}{proposta["id"]}',
        json=payload_com_linhas(proposta, [linha(militar_11gt.id)]),
        headers=auth(token),
    )

    resp = await client.delete(f'{URL}{proposta["id"]}', headers=auth(token))
    depois = await client.get(f'{URL}{proposta["id"]}', headers=auth(token))

    assert resp.status_code == HTTPStatus.OK
    assert depois.status_code == HTTPStatus.NOT_FOUND
