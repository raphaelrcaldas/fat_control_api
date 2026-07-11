"""O tripulante do FatBird só enxerga o PRÓPRIO dado.

Contraparte de `test_acesso_tripulante`: lá garantimos que o dono não é
bloqueado; aqui, que ele não vira uma porta para o dado alheio. Sem role
e sem permissões, um tripulante que troque o `user_id` na URL deve levar
403 nas leituras sensíveis (o guard é `ensure_org_permission_or_owner`:
dono passa, terceiro precisa da permissão na org).
"""

from http import HTTPStatus

import pytest

from tests.api.fatbird.conftest import auth

pytestmark = pytest.mark.anyio


def _rotas_alheias(outro_id: int):
    """(id, path, params) apontando para o dado de OUTRO militar."""
    return [
        ('cartao-saude', f'aeromedica/cartoes-saude/user/{outro_id}', None),
        ('crm', f'seg-voo/crm/user/{outro_id}', None),
        ('passaporte', f'inteligencia/passaportes/user/{outro_id}', None),
        ('dados-bancarios', f'cegep/dados-bancarios/user/{outro_id}', None),
        ('users', f'users/{outro_id}', None),
        ('logs', 'logs/user-actions', {'user_id': outro_id}),
        ('comiss', 'cegep/comiss/', {'user_id': outro_id}),
        (
            'financeiro-pgts',
            'cegep/financeiro/pgts',
            {'user_id': outro_id, 'sit': ['d', 'g'], 'page': 1, 'limit': 20},
        ),
    ]


@pytest.mark.parametrize('rota_id', [r[0] for r in _rotas_alheias(0)])
async def test_tripulante_nao_le_dado_alheio(
    client, trip_token, outro_trip, rota_id
):
    """Trocar o user_id na URL não dá acesso ao dado de outro militar."""
    outro, _ = outro_trip
    rotas = {r[0]: (r[1], r[2]) for r in _rotas_alheias(outro.id)}
    path, params = rotas[rota_id]

    resp = await client.get(
        f'/{path}', params=params, headers=auth(trip_token)
    )

    assert resp.status_code == HTTPStatus.FORBIDDEN, (
        f'{rota_id} ({path}) NÃO barrou o tripulante no dado alheio: '
        f'{resp.status_code} {resp.text}'
    )
