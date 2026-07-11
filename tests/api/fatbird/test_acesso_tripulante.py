"""Guarda de regressão: o tripulante não pode ser BLOQUEADO no FatBird.

Percorre todos os endpoints que o portal consome (`fatbird/services/api/
routes/*.ts`) com um token de tripulante real — **sem role, sem
permissões** — e exige que nenhum responda 401/403.

Por que só 401/403: o tripulante não tem `user_roles`, então qualquer
`permission_checker` numa leitura compartilhada o barra. Os fetchers do
FatBird tratam o erro como "sem dado", então a página mostra "tudo em
ordem" / vazio em vez de falhar — regressão silenciosa. Foi exatamente
assim que `cartoes-saude/user/{id}` quebrou.

404 (sem cadastro) e 422 (validação de query) são aceitáveis: significam
que a requisição CHEGOU no handler, que é o que este teste garante.
"""

from http import HTTPStatus

import pytest

from tests.api.fatbird.conftest import auth

pytestmark = pytest.mark.anyio

BLOQUEIO = {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}


def _rotas(uid: int, trip_id: int, func: str):
    """(id, path, params) de cada GET que o FatBird dispara."""
    return [
        # perfil / vínculo
        ('trips-me', 'ops/trips/me', None),
        ('users-me', 'users/me', None),
        ('users-self', f'users/{uid}', None),
        # documentos (cartoes.ts)
        ('cartao-saude', f'aeromedica/cartoes-saude/user/{uid}', None),
        ('crm', f'seg-voo/crm/user/{uid}', None),
        ('passaporte', f'inteligencia/passaportes/user/{uid}', None),
        # cegep.ts
        ('comiss-lista', 'cegep/comiss/', {'user_id': uid}),
        ('dados-bancarios', f'cegep/dados-bancarios/user/{uid}', None),
        (
            'financeiro-pgts',
            'cegep/financeiro/pgts',
            {'user_id': uid, 'sit': ['d', 'g'], 'page': 1, 'limit': 20},
        ),
        # indisp.ts
        ('indisp-self', f'indisp/user/{uid}', None),
        ('indisp-lista', 'indisp/', {'funcao': func}),
        # logs.ts
        ('logs', 'logs/user-actions', {'user_id': uid}),
        # quads.ts
        ('quads-types', 'ops/quads/types', None),
        ('quads-trip', f'ops/quads/trip/{trip_id}', {'type_id': 1}),
        # sebo.ts
        ('sebo', 'estatistica/sebo/', {'func': func}),
    ]


@pytest.mark.parametrize(
    'rota_id',
    [r[0] for r in _rotas(0, 0, 'pil')],
)
async def test_tripulante_nao_e_bloqueado(
    client, trip_user, trip_token, rota_id
):
    """Nenhum endpoint do FatBird responde 401/403 ao próprio tripulante."""
    user, trip = trip_user
    rotas = {r[0]: (r[1], r[2]) for r in _rotas(user.id, trip.id, trip.func)}
    path, params = rotas[rota_id]

    resp = await client.get(
        f'/{path}', params=params, headers=auth(trip_token)
    )

    assert resp.status_code not in BLOQUEIO, (
        f'{rota_id} ({path}) bloqueou o tripulante com '
        f'{resp.status_code}: {resp.text}'
    )
