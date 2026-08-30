"""Emissão de `quadro.recebido` no POST /ops/quads/ (único evento da v1).

O que precisa valer:

- **uma** notificação por tripulante por lote (o POST é em lote; uma por
  quadrinho viraria dezenas de itens de ruído no sino);
- quem lança **não** se auto-notifica;
- a notificação nasce com audiência `tripulante` (só o FatBird a vê);
- ela vive no MESMO commit da mutação — lote rejeitado não deixa
  notificação órfã de um quadrinho que não existe.
"""

from datetime import date, timedelta
from http import HTTPStatus

import pytest
from sqlalchemy import func, select

from fcontrol_api.enums.notificacao import NotifAudiencia, NotifTipo
from fcontrol_api.models.shared.notificacao import Notificacao
from tests.api.notificacoes.conftest import ORG, auth

pytestmark = pytest.mark.anyio


def _quad(trip_id, dias=0, type_id=1):
    return {
        'value': (date.today() + timedelta(days=dias)).isoformat(),
        'type_id': type_id,
        'description': 'x',
        'trip_id': trip_id,
    }


async def _notifs_de(session, user_id):
    result = await session.scalars(
        select(Notificacao).where(Notificacao.user_id == user_id)
    )
    return list(result.all())


async def test_lote_gera_uma_notificacao_por_tipo(
    client, session, users, trips, token
):
    """O caso real da tela: um tipo, várias datas — 1 notificação.

    O `QuadForm` do client sempre lança UM tipo para UM tripulante,
    variando só a quantidade (intervalo de datas ou lastros). O
    agrupamento por (tripulante, tipo) transforma isso num item só,
    com a contagem no título.
    """
    _, other_user = users
    _, other_trip = trips

    response = await client.post(
        '/ops/quads/',
        json=[
            _quad(other_trip.id, 0, type_id=1),
            _quad(other_trip.id, 1, type_id=1),
            _quad(other_trip.id, 2, type_id=1),
        ],
        headers=auth(token),
    )
    assert response.status_code == HTTPStatus.CREATED

    notifs = await _notifs_de(session, other_user.id)
    assert len(notifs) == 1

    notif = notifs[0]
    assert notif.tipo == NotifTipo.QUADRO_RECEBIDO.value
    assert notif.audiencia == NotifAudiencia.TRIPULANTE.value
    assert notif.recurso == 'ops.quadro'
    assert notif.uae == ORG
    assert '3' in notif.titulo

    # Contrato do payload — é dele que o FatBird monta o deep-link
    # (/ops/quads?tipo=&func=) e o rótulo "Sobreaviso: PRETO".
    assert notif.payload['quantidade'] == 3
    # UM tipo por notificação (id + nome + grupo). O nome vai CRU: a caixa
    # alta é aplicada na exibição, não gravada no dado.
    assert notif.payload['tipo'] == {
        'id': 1,
        'nome': 'preto',
        'grupo': 'sobreaviso',
    }
    assert notif.payload['func'] == other_trip.func


async def test_lote_misto_gera_uma_notificacao_por_tipo(
    client, session, users, trips, token
):
    """Tipos diferentes no mesmo lote não se fundem num item só.

    A tela não faz isso hoje, mas o endpoint aceita — e uma notificação
    com dois tipos teria de eleger um deles para o deep-link, por acaso.
    """
    _, other_user = users
    _, other_trip = trips

    response = await client.post(
        '/ops/quads/',
        json=[
            _quad(other_trip.id, 0, type_id=1),
            _quad(other_trip.id, 1, type_id=1),
            _quad(other_trip.id, 2, type_id=2),
        ],
        headers=auth(token),
    )
    assert response.status_code == HTTPStatus.CREATED

    notifs = await _notifs_de(session, other_user.id)
    assert len(notifs) == 2

    por_tipo = {n.payload['tipo']['id']: n for n in notifs}
    assert set(por_tipo) == {1, 2}
    assert por_tipo[1].payload['quantidade'] == 2
    assert por_tipo[2].payload['quantidade'] == 1
    assert por_tipo[2].payload['tipo']['nome'] == 'vermelho'


async def test_autor_nao_se_auto_notifica(
    client, session, users, trips, token
):
    """Quem lançou o próprio quadrinho não recebe 'você recebeu'."""
    user, _ = users
    trip, _ = trips

    response = await client.post(
        '/ops/quads/', json=[_quad(trip.id)], headers=auth(token)
    )
    assert response.status_code == HTTPStatus.CREATED

    assert await _notifs_de(session, user.id) == []


async def test_lote_misto_notifica_so_os_outros(
    client, session, users, trips, token
):
    """Lote com autor + terceiro: uma notificação, só para o terceiro."""
    user, other_user = users
    trip, other_trip = trips

    response = await client.post(
        '/ops/quads/',
        json=[
            _quad(trip.id, 0),
            _quad(other_trip.id, 0),
            _quad(other_trip.id, 1),
        ],
        headers=auth(token),
    )
    assert response.status_code == HTTPStatus.CREATED

    total = await session.scalar(select(func.count()).select_from(Notificacao))
    assert total == 1
    assert await _notifs_de(session, user.id) == []

    (notif,) = await _notifs_de(session, other_user.id)
    assert notif.payload['quantidade'] == 2
    assert notif.created_by == user.id


async def test_lote_rejeitado_nao_deixa_notificacao(
    client, session, users, trips, token
):
    """Duplicata aborta o lote inteiro — e a notificação vai junto.

    Emissão e mutação compartilham o commit: se o quadrinho não existe, a
    notificação dele não pode sobrar.
    """
    _, other_user = users
    _, other_trip = trips

    primeiro = await client.post(
        '/ops/quads/', json=[_quad(other_trip.id)], headers=auth(token)
    )
    assert primeiro.status_code == HTTPStatus.CREATED
    assert len(await _notifs_de(session, other_user.id)) == 1

    # Segundo lote com uma duplicata exata -> 400 antes de qualquer insert.
    segundo = await client.post(
        '/ops/quads/',
        json=[_quad(other_trip.id, 5), _quad(other_trip.id, 0)],
        headers=auth(token),
    )
    assert segundo.status_code == HTTPStatus.BAD_REQUEST

    # Continua só a notificação do primeiro lote.
    assert len(await _notifs_de(session, other_user.id)) == 1


async def test_lote_vazio_nao_notifica(client, session, token):
    """Lote vazio é aceito e não emite nada."""
    response = await client.post('/ops/quads/', json=[], headers=auth(token))

    assert response.status_code == HTTPStatus.CREATED
    total = await session.scalar(select(func.count()).select_from(Notificacao))
    assert total == 0
