"""
Testes para o endpoint PUT /cegep/comiss/{comiss_id}.

Este endpoint atualiza um comissionamento existente.
Requer autenticacao.

Regras de negocio:
- Nao pode haver conflito de datas com outros comissionamentos
- Nao pode excluir missoes do escopo ao alterar datas
"""

from datetime import date, datetime, timedelta
from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.cegep.comiss import Comissionamento
from tests.factories import ComissFactory, FragMisFactory, UserFragFactory

pytestmark = pytest.mark.anyio


@pytest.fixture
async def comiss_existente(session, users):
    """Cria um comissionamento para testes de update."""
    user, _ = users
    today = date.today()

    comiss = ComissFactory(
        user_id=user.id,
        data_ab=today,
        data_fc=today + timedelta(days=90),
    )
    session.add(comiss)
    await session.commit()
    await session.refresh(comiss)

    return comiss


async def test_update_comiss_success(
    client, session, token, users, comiss_existente
):
    """Testa atualizacao de comissionamento com sucesso."""
    user, _ = users
    new_data_fc = (date.today() + timedelta(days=120)).isoformat()

    update_data = {
        'user_id': user.id,
        'status': 'aberto',
        'dep': True,
        'data_ab': comiss_existente.data_ab.isoformat(),
        'qtd_aj_ab': 35.0,
        'valor_aj_ab': 6000.00,
        'data_fc': new_data_fc,
        'qtd_aj_fc': 35.0,
        'valor_aj_fc': 6000.00,
        'dias_cumprir': 70,
        'doc_prop': comiss_existente.doc_prop,
        'doc_aut': comiss_existente.doc_aut,
        'doc_enc': 'ENC-0001/2025',
    }

    response = await client.put(
        f'/cegep/comiss/{comiss_existente.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert 'atualizado' in resp['message'].lower()

    # Verifica no banco
    await session.refresh(comiss_existente)
    assert comiss_existente.dep is True
    assert comiss_existente.valor_aj_ab == 6000.00
    assert comiss_existente.doc_enc == 'ENC-0001/2025'


async def test_update_comiss_not_found(client, token, users):
    """Testa atualizacao de comissionamento inexistente."""
    user, _ = users

    update_data = {
        'user_id': user.id,
        'status': 'aberto',
        'dep': False,
        'data_ab': date.today().isoformat(),
        'qtd_aj_ab': 30.0,
        'valor_aj_ab': 5000.00,
        'data_fc': (date.today() + timedelta(days=90)).isoformat(),
        'qtd_aj_fc': 30.0,
        'valor_aj_fc': 5000.00,
        'dias_cumprir': 60,
        'doc_prop': 'PROP-0001/2025',
        'doc_aut': 'AUT-0001/2025',
        'doc_enc': None,
    }

    response = await client.put(
        '/cegep/comiss/99999',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert 'encontrado' in resp['message'].lower()


async def test_update_comiss_date_conflict(
    client, session, token, users, comiss_existente
):
    """Testa que nao permite update com conflito de datas."""
    user, _ = users
    today = date.today()

    # Cria outro comissionamento (fechado) no futuro
    outro_comiss = ComissFactory(
        user_id=user.id,
        status='fechado',
        data_ab=today + timedelta(days=100),
        data_fc=today + timedelta(days=180),
    )
    session.add(outro_comiss)
    await session.commit()

    # Tenta atualizar com datas que conflitam
    update_data = {
        'user_id': user.id,
        'status': 'aberto',
        'dep': False,
        'data_ab': comiss_existente.data_ab.isoformat(),
        'qtd_aj_ab': 30.0,
        'valor_aj_ab': 5000.00,
        'data_fc': (today + timedelta(days=150)).isoformat(),  # Conflita
        'qtd_aj_fc': 30.0,
        'valor_aj_fc': 5000.00,
        'dias_cumprir': 60,
        'doc_prop': 'PROP-0001/2025',
        'doc_aut': 'AUT-0001/2025',
        'doc_enc': None,
    }

    response = await client.put(
        f'/cegep/comiss/{comiss_existente.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert 'conflito' in resp['message'].lower()


async def test_update_comiss_missoes_fora_escopo(
    client, session, token, users, comiss_existente
):
    """Testa que nao permite alterar datas excluindo missoes do escopo."""
    user, _ = users

    # Cria missao dentro do periodo atual
    afast = datetime.now() + timedelta(days=30)
    regres = datetime.now() + timedelta(days=33)

    missao = FragMisFactory(afast=afast, regres=regres)
    session.add(missao)
    await session.commit()
    await session.refresh(missao)

    user_frag = UserFragFactory(
        frag_id=missao.id,
        user_id=user.id,
        sit='c',
        p_g=user.p_g,
    )
    session.add(user_frag)
    await session.commit()

    # Tenta alterar data_fc para antes da missao
    update_data = {
        'user_id': user.id,
        'status': 'aberto',
        'dep': False,
        'data_ab': comiss_existente.data_ab.isoformat(),
        'qtd_aj_ab': 30.0,
        'valor_aj_ab': 5000.00,
        'data_fc': (date.today() + timedelta(days=20)).isoformat(),
        'qtd_aj_fc': 30.0,
        'valor_aj_fc': 5000.00,
        'dias_cumprir': 60,
        'doc_prop': 'PROP-0001/2025',
        'doc_aut': 'AUT-0001/2025',
        'doc_enc': None,
    }

    response = await client.put(
        f'/cegep/comiss/{comiss_existente.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    resp = response.json()
    assert 'fora do escopo' in resp['message'].lower()


async def test_update_comiss_close_status(
    client, session, token, users, comiss_existente
):
    """Testa fechamento de comissionamento."""
    user, _ = users

    update_data = {
        'user_id': user.id,
        'status': 'fechado',
        'dep': comiss_existente.dep,
        'data_ab': comiss_existente.data_ab.isoformat(),
        'qtd_aj_ab': comiss_existente.qtd_aj_ab,
        'valor_aj_ab': comiss_existente.valor_aj_ab,
        'data_fc': comiss_existente.data_fc.isoformat(),
        'qtd_aj_fc': comiss_existente.qtd_aj_fc,
        'valor_aj_fc': comiss_existente.valor_aj_fc,
        'dias_cumprir': comiss_existente.dias_cumprir,
        'doc_prop': comiss_existente.doc_prop,
        'doc_aut': comiss_existente.doc_aut,
        'doc_enc': 'ENC-0001/2025',
    }

    response = await client.put(
        f'/cegep/comiss/{comiss_existente.id}',
        headers={'Authorization': f'Bearer {token}'},
        json=update_data,
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica no banco
    db_comiss = await session.scalar(
        select(Comissionamento).where(
            Comissionamento.id == comiss_existente.id
        )
    )
    assert db_comiss.status == 'fechado'


async def test_update_comiss_without_token(client, session, users):
    """Testa que requisicao sem token falha."""
    user, _ = users

    comiss = ComissFactory(user_id=user.id)
    session.add(comiss)
    await session.commit()
    await session.refresh(comiss)

    update_data = {
        'user_id': user.id,
        'status': 'fechado',
        'dep': False,
        'data_ab': comiss.data_ab.isoformat(),
        'qtd_aj_ab': 30.0,
        'valor_aj_ab': 5000.00,
        'data_fc': comiss.data_fc.isoformat(),
        'qtd_aj_fc': 30.0,
        'valor_aj_fc': 5000.00,
        'dias_cumprir': 60,
        'doc_prop': 'PROP-0001/2025',
        'doc_aut': 'AUT-0001/2025',
        'doc_enc': None,
    }

    response = await client.put(
        f'/cegep/comiss/{comiss.id}',
        json=update_data,
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
