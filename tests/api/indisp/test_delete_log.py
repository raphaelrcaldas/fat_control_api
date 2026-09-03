"""Auditoria da remoção de indisponibilidade.

O `delete` é soft: a linha some da tela mas continua no banco. Sem o
`before` no log, o histórico registrava só "fulano removeu às tantas" —
quem lê não descobria O QUE foi removido, e o registro apagado não está
mais em lugar nenhum que a tela mostre.

`after` fica vazio de propósito: é a assimetria que distingue uma
remoção de uma alteração para quem lê o log (o front usa isso para não
desenhar uma seta apontando para o vazio).
"""

import json
from http import HTTPStatus

import pytest
from sqlalchemy import select

from fcontrol_api.models.security.logs import UserActionLog

pytestmark = pytest.mark.anyio

RESOURCE = 'ops.indisp'


async def _log_delete(session, resource_id):
    """Log de remoção do registro, se houver."""
    return await session.scalar(
        select(UserActionLog).where(
            UserActionLog.resource == RESOURCE,
            UserActionLog.resource_id == resource_id,
            UserActionLog.action == 'delete',
        )
    )


async def test_delete_registra_o_que_foi_removido(
    client, session, indisp, token
):
    """O `before` guarda o estado apagado; o `after` fica vazio."""
    response = await client.delete(
        f'/indisp/{indisp.id}',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == HTTPStatus.OK

    log = await _log_delete(session, indisp.id)
    assert log is not None, 'a remoção tem de deixar log'

    before = json.loads(log.before)
    assert before['date_start'] == str(indisp.date_start)
    assert before['date_end'] == str(indisp.date_end)
    assert before['mtv'] == indisp.mtv
    assert before['obs'] == indisp.obs

    # Sem isto o front não teria como distinguir remoção de alteração.
    assert not log.after or json.loads(log.after) == {}


async def test_delete_grava_data_como_string(client, session, indisp, token):
    """`date` não serializa em JSONB — o log guarda ISO, não repr."""
    await client.delete(
        f'/indisp/{indisp.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    log = await _log_delete(session, indisp.id)
    before = json.loads(log.before)

    assert isinstance(before['date_start'], str)
    assert before['date_start'].count('-') == 2
