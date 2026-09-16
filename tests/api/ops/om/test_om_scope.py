"""Isolamento cross-org de ordens de missão (/ops/om).

Toda OM carrega `uae`; os handlers filtram `OrdemMissao.uae == active_org`.
Um admin da '11gt' não lê nem apaga OM da '1gt' — e o teste inclui um
controle positivo (admin da '1gt' enxerga a própria OM) para garantir que
o 404 vem do escopo de org, não de rota inexistente.

O escopo vale também para o ALVO do write-path, não só para a ordem: o
id do tripulante vem do corpo da requisição, então `criar_tripulacao_batch`
filtra `Tripulante.uae` e recusa com 400 quem é de outra unidade.

(A fixture autouse `seed_aeronaves` do conftest do módulo cobre a FK de
`matricula_anv`.)
"""

from http import HTTPStatus

import pytest

from fcontrol_api.models.security.resources import UserRole
from tests.factories import OrdemMissaoFactory, TripFactory

pytestmark = pytest.mark.anyio

URL = '/ops/om/'


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
async def admin_1gt_token(users, session, make_org_token):
    _, other = users
    session.add(UserRole(user_id=other.id, role_id=1, organizacao_id='1gt'))
    await session.commit()
    return await make_org_token(other, active_org='1gt')


@pytest.fixture
async def om_1gt(session, users):
    _, other = users
    om = OrdemMissaoFactory(created_by=other.id, uae='1gt')
    session.add(om)
    await session.commit()
    await session.refresh(om)
    return om


async def test_get_by_id_cross_org_404(client, om_1gt, token):
    resp = await client.get(f'{URL}{om_1gt.id}', headers=_auth(token))
    assert resp.status_code == HTTPStatus.NOT_FOUND


async def test_delete_cross_org_404(client, om_1gt, token):
    resp = await client.delete(f'{URL}{om_1gt.id}', headers=_auth(token))
    assert resp.status_code == HTTPStatus.NOT_FOUND
    # Prova que caiu no handler (escopo), não em rota inexistente.
    assert resp.json()['message'] == 'Ordem de missão não encontrada'


async def test_org_dona_enxerga_a_propria_om(client, om_1gt, admin_1gt_token):
    """Controle positivo: admin da '1gt' vê a OM que a '11gt' não vê."""
    resp = await client.get(
        f'{URL}{om_1gt.id}', headers=_auth(admin_1gt_token)
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['id'] == om_1gt.id


@pytest.fixture
async def trip_1gt(session, users):
    """Tripulante da '1gt' — alvo cross-org para o write-path da OM."""
    _, other = users
    trip = TripFactory(user_id=other.id, uae='1gt')
    session.add(trip)
    await session.commit()
    await session.refresh(trip)
    return trip


def _payload_om(tripulacao):
    return {
        'matricula_anv': '2850',
        'tipo': 'instrucao',
        'projeto': 'KC-390',
        'status': 'rascunho',
        'esf_aer': 90,
        'campos_especiais': [],
        'etapas': [
            {
                'dt_dep': '2025-06-15T10:00:00',
                'origem': 'SBGL',
                'dest': 'SBBR',
                'dt_arr': '2025-06-15T11:30:00',
                'alternativa': 'SBCF',
                'tvoo_alt': 30,
                'qtd_comb': 15,
                'esf_aer': 'normal',
            }
        ],
        'tripulacao': tripulacao,
        'etiquetas_ids': [],
    }


async def test_create_com_tripulante_de_outra_org_400(client, trip_1gt, token):
    """O gate autoriza a AÇÃO, não o ALVO: o id vem do corpo.

    Sem escopo de `uae` na busca do tripulante, a OM nascia na '11gt'
    com um militar da '1gt' anexado — e o GET seguinte devolvia nome,
    id_fab e posto dele.
    """
    resp = await client.post(
        URL,
        json=_payload_om({'pil': [trip_1gt.id]}),
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    # Prova que caiu no handler, não em rota inexistente. A mensagem é
    # neutra de propósito: não revela que o id existe em outra unidade.
    assert resp.json()['message'] == (
        f'Tripulante {trip_1gt.id} não encontrado'
    )


async def test_update_com_tripulante_de_outra_org_400(
    client, session, users, trip_1gt, token
):
    """O mesmo escopo vale na edição, que apaga e recria a tripulação."""
    user, _ = users
    om = OrdemMissaoFactory(created_by=user.id, uae='11gt')
    session.add(om)
    await session.commit()
    await session.refresh(om)

    resp = await client.put(
        f'{URL}{om.id}',
        json={'tripulacao': {'pil': [trip_1gt.id]}},
        headers=_auth(token),
    )
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert resp.json()['message'] == (
        f'Tripulante {trip_1gt.id} não encontrado'
    )
