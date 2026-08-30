"""Emissão de `quadro.removido` no DELETE /ops/quads/.

O lançamento avisa que o quadrinho chegou; a remoção precisa avisar que
ele saiu, senão o tripulante fica com um aviso na bandeja apontando para
um registro que não existe mais.

As regras espelham as do lançamento: agrupado por (tripulante, tipo),
audiência `tripulante`, quem apaga não se auto-notifica, e tudo no mesmo
commit da mutação.
"""

from datetime import date, timedelta
from http import HTTPStatus

import pytest
from sqlalchemy import select

from fcontrol_api.enums.notificacao import NotifAudiencia, NotifTipo
from fcontrol_api.models.shared.notificacao import Notificacao
from fcontrol_api.models.shared.quads import Quad
from tests.api.notificacoes.conftest import ORG, auth
from tests.factories import TripFactory, UserFactory

pytestmark = pytest.mark.anyio


async def _mk_quads(session, trip_id, *, type_id=1, qtd=1):
    quads = [
        Quad(
            value=date.today() + timedelta(days=i),
            description='x',
            type_id=type_id,
            trip_id=trip_id,
        )
        for i in range(qtd)
    ]
    session.add_all(quads)
    await session.commit()
    for q in quads:
        await session.refresh(q)
    return quads


async def _remocoes_de(session, user_id):
    result = await session.scalars(
        select(Notificacao).where(
            Notificacao.user_id == user_id,
            Notificacao.tipo == NotifTipo.QUADRO_REMOVIDO.value,
        )
    )
    return list(result.all())


async def test_remocao_notifica_o_tripulante(
    client, session, users, trips, token
):
    """Dois quadrinhos do mesmo tipo saem como UM aviso, com a contagem."""
    _, other_user = users
    _, other_trip = trips
    quads = await _mk_quads(session, other_trip.id, type_id=1, qtd=2)

    response = await client.request(
        'DELETE',
        '/ops/quads/',
        json={'ids': [q.id for q in quads]},
        headers=auth(token),
    )
    assert response.status_code == HTTPStatus.OK

    notifs = await _remocoes_de(session, other_user.id)
    assert len(notifs) == 1

    notif = notifs[0]
    assert notif.audiencia == NotifAudiencia.TRIPULANTE.value
    assert notif.uae == ORG
    assert notif.recurso == 'ops.quadro'
    assert '2' in notif.titulo
    # Mesmo contrato de payload do lançamento — o FatBird monta o rótulo
    # e o deep-link do mesmo jeito nos dois eventos.
    assert notif.payload['quantidade'] == 2
    assert notif.payload['tipo'] == {
        'id': 1,
        'nome': 'preto',
        'grupo': 'sobreaviso',
    }
    assert notif.payload['func'] == other_trip.func


async def test_remocao_agrupa_por_tipo(client, session, users, trips, token):
    """Tipos diferentes na mesma remoção viram avisos separados."""
    _, other_user = users
    _, other_trip = trips
    quads = await _mk_quads(session, other_trip.id, type_id=1, qtd=2)
    quads += await _mk_quads(session, other_trip.id, type_id=2, qtd=1)

    response = await client.request(
        'DELETE',
        '/ops/quads/',
        json={'ids': [q.id for q in quads]},
        headers=auth(token),
    )
    assert response.status_code == HTTPStatus.OK

    notifs = await _remocoes_de(session, other_user.id)
    por_tipo = {n.payload['tipo']['id']: n for n in notifs}
    assert set(por_tipo) == {1, 2}
    assert por_tipo[1].payload['quantidade'] == 2
    assert por_tipo[2].payload['tipo']['nome'] == 'vermelho'


async def test_quem_apaga_nao_se_auto_notifica(
    client, session, users, trips, token
):
    """Mesma regra do lançamento: o autor da ação não recebe o aviso."""
    user, _ = users
    trip, _ = trips
    quads = await _mk_quads(session, trip.id)

    response = await client.request(
        'DELETE',
        '/ops/quads/',
        json={'ids': [q.id for q in quads]},
        headers=auth(token),
    )
    assert response.status_code == HTTPStatus.OK

    assert await _remocoes_de(session, user.id) == []


async def test_remocao_de_outra_org_nao_apaga_nem_notifica(
    client, session, users, token
):
    """Quad de tripulante de outra unidade: 404, sem apagar nem avisar."""
    outro = UserFactory(unidade='1gt')
    session.add(outro)
    await session.flush()
    trip_1gt = TripFactory(user_id=outro.id, uae='1gt', proj='c-130')
    session.add(trip_1gt)
    await session.commit()
    await session.refresh(trip_1gt)

    quads = await _mk_quads(session, trip_1gt.id)

    response = await client.request(
        'DELETE',
        '/ops/quads/',
        json={'ids': [q.id for q in quads]},
        headers=auth(token),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert await _remocoes_de(session, outro.id) == []
    sobrou = await session.scalar(select(Quad).where(Quad.id == quads[0].id))
    assert sobrou is not None
