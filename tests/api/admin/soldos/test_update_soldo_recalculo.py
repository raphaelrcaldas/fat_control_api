"""Efeito colateral do PUT /admin/soldos/{id}: quem é recalculado.

Complementa `test_janela_recalculo.py` (decisão sobre datas, sem banco)
verificando o comportamento observável do endpoint: só as missões dentro
da janela têm o cache `custos` materializado.

O soldo destes testes é de `tb`, o único posto do seed sem soldo cadastrado
(`tests/seed/soldos.py`) — assim a faixa pode ser esticada, encurtada e
reaberta à vontade sem esbarrar na `ExcludeConstraint` de sobreposição.
"""

from datetime import date, datetime, time
from http import HTTPStatus

import pytest

from fcontrol_api.models.shared.posto_grad import Soldo
from tests.factories import (
    FragMisFactory,
    PernoiteFragFactory,
    UserFragFactory,
)

pytestmark = pytest.mark.anyio

VIGENCIA_INICIO = date(2024, 1, 1)
VIGENCIA_FIM = date(2024, 6, 30)


@pytest.fixture
async def soldo_tb(session):
    """Soldo de faixa fechada, isolado dos soldos do seed."""
    soldo = Soldo(
        pg='tb',
        valor=15000.00,
        data_inicio=VIGENCIA_INICIO,
        data_fim=VIGENCIA_FIM,
    )
    session.add(soldo)
    await session.commit()
    await session.refresh(soldo)
    return soldo


async def _missao(session, *, n_doc, user, ini, fim):
    """Missão de um pernoite, com militar em gratificação (`sit='g'`).

    Nasce com `custos` vazio: é o sentinela do teste — se ganhar conteúdo,
    a missão foi varrida pelo recálculo.
    """
    missao = FragMisFactory(
        n_doc=n_doc,
        tipo_doc='om',
        tipo='adm',
        acrec_desloc=False,
        indenizavel=True,
        afast=datetime.combine(ini, time(8, 0)),
        regres=datetime.combine(fim, time(18, 0)),
    )
    session.add(missao)
    await session.flush()

    session.add(
        PernoiteFragFactory(
            frag_id=missao.id,
            cidade_id=3550308,
            data_ini=ini,
            data_fim=fim,
            acrec_desloc=False,
            meia_diaria=False,
            obs='',
        )
    )
    session.add(
        UserFragFactory(
            frag_id=missao.id, user_id=user.id, sit='g', p_g=user.p_g
        )
    )
    await session.commit()
    await session.refresh(missao)
    assert not missao.custos
    return missao


async def test_estender_data_fim_recalcula_so_a_janela(
    client, session, token_sistema, soldo_tb, users
):
    """Esticar a `data_fim` varre só o trecho novo, não a vigência toda.

    Empurrar o fim de 30/06 para 31/07 só pode mudar o custo das missões
    nesse mês — a missão de fevereiro continua no mesmo soldo, com o mesmo
    valor, e não precisa ser varrida. É daqui que vem o ganho: numa faixa
    que começa em 2019, a alternativa era varrer seis anos de missões.
    """
    user, _ = users

    dentro = await _missao(
        session,
        n_doc='7201',
        user=user,
        ini=date(2024, 7, 10),
        fim=date(2024, 7, 13),
    )
    fora = await _missao(
        session,
        n_doc='7202',
        user=user,
        ini=date(2024, 2, 10),
        fim=date(2024, 2, 13),
    )

    response = await client.put(
        f'/admin/soldos/{soldo_tb.id}',
        headers={'Authorization': f'Bearer {token_sistema}'},
        json={'data_fim': '2024-07-31'},
    )

    assert response.status_code == HTTPStatus.OK

    await session.refresh(dentro)
    await session.refresh(fora)
    assert dentro.custos
    assert not fora.custos


async def test_reabrir_vigencia_recalcula_ate_o_fim(
    client, session, token_sistema, soldo_tb, users
):
    """`data_fim` → NULL varre tudo daí em diante, sem limite superior.

    Regressão: a versão anterior calculava `fim = max(fins)` e parava no
    fim antigo, então uma missão bem depois dele ficava com o custo do
    soldo seguinte — que, reaberta a vigência, não vale mais.
    """
    user, _ = users

    bem_depois = await _missao(
        session,
        n_doc='7203',
        user=user,
        ini=date(2025, 9, 10),
        fim=date(2025, 9, 13),
    )

    response = await client.put(
        f'/admin/soldos/{soldo_tb.id}',
        headers={'Authorization': f'Bearer {token_sistema}'},
        json={'data_fim': None},
    )

    assert response.status_code == HTTPStatus.OK

    await session.refresh(bem_depois)
    assert bem_depois.custos


async def test_submit_sem_alteracao_nao_recalcula(
    client, session, token_sistema, soldo_tb, users
):
    """Reenviar os mesmos valores não varre missão nenhuma.

    O formulário do front manda os quatro campos a cada submit, então
    `exclude_unset` não distingue "reenviado igual" de "alterado" — sem a
    comparação contra o banco, todo "salvar" pagaria a varredura inteira.
    """
    user, _ = users

    missao = await _missao(
        session,
        n_doc='7204',
        user=user,
        ini=date(2024, 2, 10),
        fim=date(2024, 2, 13),
    )

    response = await client.put(
        f'/admin/soldos/{soldo_tb.id}',
        headers={'Authorization': f'Bearer {token_sistema}'},
        json={
            'pg': soldo_tb.pg,
            'valor': float(soldo_tb.valor),
            'data_inicio': VIGENCIA_INICIO.isoformat(),
            'data_fim': VIGENCIA_FIM.isoformat(),
        },
    )

    assert response.status_code == HTTPStatus.OK

    await session.refresh(missao)
    assert not missao.custos


async def test_mudanca_de_valor_recalcula_a_vigencia_inteira(
    client, session, token_sistema, soldo_tb, users
):
    """Trocar o valor atinge todos os dias da faixa, não só as pontas."""
    user, _ = users

    inicio_da_faixa = await _missao(
        session,
        n_doc='7205',
        user=user,
        ini=date(2024, 1, 5),
        fim=date(2024, 1, 8),
    )
    fim_da_faixa = await _missao(
        session,
        n_doc='7206',
        user=user,
        ini=date(2024, 6, 20),
        fim=date(2024, 6, 23),
    )

    response = await client.put(
        f'/admin/soldos/{soldo_tb.id}',
        headers={'Authorization': f'Bearer {token_sistema}'},
        json={'valor': 17000.00},
    )

    assert response.status_code == HTTPStatus.OK

    await session.refresh(inicio_da_faixa)
    await session.refresh(fim_da_faixa)
    assert inicio_da_faixa.custos
    assert fim_da_faixa.custos
