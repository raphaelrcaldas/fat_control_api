"""Pendencias historicas separadas entre voo e simulador, por organizacao."""

from datetime import date, time
from http import HTTPStatus

import pytest
from sqlalchemy import select

from fcontrol_api.models.estatistica.etapa import Etapa, Missao, TripEtapa
from fcontrol_api.models.shared.aeronaves import Aeronave
from tests.factories import TripFactory, UserFactory

pytestmark = pytest.mark.anyio
URL = '/estatistica/etapas/pendentes'


@pytest.fixture
async def pendencias(session):
    session.add(Aeronave(matricula='9990', active=True, sit='DI', obs=None))
    voo = Missao(titulo='Voo', obs=None, uae='11gt')
    antiga = Missao(
        titulo='Simulador antigo', obs=None, uae='11gt', is_simulador=True
    )
    recente = Missao(
        titulo='Simulador recente', obs=None, uae='11gt', is_simulador=True
    )
    externa = Missao(
        titulo='Outra org', obs=None, uae='1gt', is_simulador=True
    )
    session.add_all([voo, antiga, recente, externa])
    await session.flush()

    def etapa(missao, dia, sagem, parte1):
        return Etapa(
            missao_id=missao.id,
            obs=None,
            data=dia,
            origem='SBGL',
            destino='SBGL',
            dep=time(8),
            arr=time(9),
            anv='9990',
            pousos=1,
            tow=None,
            pax=None,
            carga=None,
            comb=None,
            lub=None,
            nivel=None,
            sagem=sagem,
            parte1=parte1,
        )

    primeira = etapa(antiga, date(2024, 1, 1), False, True)
    session.add_all([
        primeira,
        etapa(antiga, date(2024, 2, 1), True, False),
        etapa(antiga, date(2026, 9, 1), True, True),
        etapa(recente, date(2026, 9, 2), False, False),
        etapa(voo, date(2026, 9, 3), False, False),
        etapa(externa, date(2023, 1, 1), False, False),
    ])
    await session.commit()
    return voo, antiga, recente, primeira


async def test_simulador_agrupa_historico_e_isola_org(
    client, token, pendencias
):
    _, antiga, recente, primeira = pendencias
    response = await client.get(
        URL,
        params={'is_simulador': 'true'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert data['total'] == 3
    assert data['total_missoes'] == 2
    assert [m['missao_id'] for m in data['missoes']] == [
        antiga.id,
        recente.id,
    ]
    assert data['missoes'][0] == {
        'missao_id': antiga.id,
        'titulo': antiga.titulo,
        'etapa_id': primeira.id,
        'primeira_data': '2024-01-01',
        'ultima_data': '2024-02-01',
        'total': 2,
        'trigramas': [],
    }


async def test_default_continua_somente_voos(client, token, pendencias):
    voo, _, _, _ = pendencias
    response = await client.get(
        URL, headers={'Authorization': f'Bearer {token}'}
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert data['total'] == 1
    assert data['total_missoes'] == 1
    assert data['missoes'][0]['missao_id'] == voo.id
    assert data['missoes'][0]['trigramas'] == []


async def test_limite_nao_reduz_totais_simulador(client, token, pendencias):
    _, antiga, _, _ = pendencias
    response = await client.get(
        URL,
        params={'is_simulador': 'true', 'limit': 1},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    data = response.json()['data']
    assert data['total'] == 3
    assert data['total_missoes'] == 2
    assert [m['missao_id'] for m in data['missoes']] == [antiga.id]


async def test_pendencias_simulador_exigem_permissao(client, token_sem_perm):
    response = await client.get(
        URL,
        params={'is_simulador': 'true'},
        headers={'Authorization': f'Bearer {token_sem_perm}'},
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


@pytest.fixture
async def dupla(session, pendencias):
    """Dupla na missao de simulador antiga, com o moderno inserido primeiro.

    O moderno so voa a etapa ja verificada (nao pendente) e o antigo voa a
    pendente e a verificada: prova que o trigrama vem de TODAS as etapas e
    que a ordem e por antiguidade, nao por insercao.
    """
    _, antiga, _, _ = pendencias
    trips = {}
    for chave, p_g, trig in (
        ('moderno', '3s', 'ZZM'),
        ('antigo', '1t', 'AAA'),
    ):
        user = UserFactory(p_g=p_g)
        session.add(user)
        await session.flush()
        trip = TripFactory(user_id=user.id, trig=trig)
        session.add(trip)
        await session.flush()
        trips[chave] = trip.id

    etapas = (
        await session.scalars(
            select(Etapa)
            .where(Etapa.missao_id == antiga.id)
            .order_by(Etapa.data)
        )
    ).all()
    pendente, pendente_b, verificada = etapas
    for etapa, chave in (
        (verificada, 'moderno'),
        (pendente, 'antigo'),
        (pendente_b, 'antigo'),
        (verificada, 'antigo'),
    ):
        session.add(
            TripEtapa(
                etapa_id=etapa.id,
                trip_id=trips[chave],
                func='mc',
                func_bordo='MC',
            )
        )
    await session.commit()


async def test_simulador_devolve_trigramas_por_antiguidade(
    client, token, pendencias, dupla
):
    _, antiga, recente, _ = pendencias
    response = await client.get(
        URL,
        params={'is_simulador': 'true'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    por_id = {m['missao_id']: m for m in response.json()['data']['missoes']}
    # 1t (AAA) mais antigo que 3s (ZZM), sem repetir AAA das 3 etapas.
    assert por_id[antiga.id]['trigramas'] == ['AAA', 'ZZM']
    assert por_id[recente.id]['trigramas'] == []


async def test_voo_nao_devolve_trigramas(client, token, pendencias, dupla):
    response = await client.get(
        URL, headers={'Authorization': f'Bearer {token}'}
    )

    assert response.status_code == HTTPStatus.OK
    assert [m['trigramas'] for m in response.json()['data']['missoes']] == [[]]


async def test_trigramas_empate_total_desempata_por_id_do_tripulante(
    client, token, session, pendencias
):
    """Mesmo posto, mesma `ult_promo` e `ant_rel` nulo: decide o trip_id.

    Espelha o client (`ant_rel` nulo = 0 e desempate por `trip_id`). O
    trigrama do menor id e alfabeticamente o ultimo, e o de maior id e
    inserido antes na tabela de ligacao: nada alem do id explica a ordem.
    """
    _, _, recente, _ = pendencias
    etapa = await session.scalar(
        select(Etapa).where(Etapa.missao_id == recente.id)
    )
    trips = []
    for trig in ('ZZY', 'AAB'):
        user = UserFactory(p_g='1t', ult_promo=date(2015, 1, 1), ant_rel=None)
        session.add(user)
        await session.flush()
        trip = TripFactory(user_id=user.id, trig=trig)
        session.add(trip)
        await session.flush()
        trips.append(trip.id)
    assert trips[0] < trips[1]

    for trip_id in reversed(trips):
        session.add(
            TripEtapa(
                etapa_id=etapa.id,
                trip_id=trip_id,
                func='mc',
                func_bordo='MC',
            )
        )
    await session.commit()

    response = await client.get(
        URL,
        params={'is_simulador': 'true'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    por_id = {m['missao_id']: m for m in response.json()['data']['missoes']}
    assert por_id[recente.id]['trigramas'] == ['ZZY', 'AAB']


async def _trigramas_ordenados(client, token, session, recente, specs):
    """Vincula tripulantes do mesmo posto a etapa de `recente` e lista.

    `specs` = [(trig, ult_promo, ant_rel)], na ordem de criacao (= ordem
    crescente de id). A ligacao e inserida na mesma ordem, entao nem id,
    nem insercao, nem ordem alfabetica podem ser o que explica o resultado
    de cada caso: so `ult_promo`/`ant_rel` no `order_by`.
    """
    etapa = await session.scalar(
        select(Etapa).where(Etapa.missao_id == recente.id)
    )
    for trig, ult_promo, ant_rel in specs:
        user = UserFactory(p_g='1t', ult_promo=ult_promo, ant_rel=ant_rel)
        session.add(user)
        await session.flush()
        trip = TripFactory(user_id=user.id, trig=trig)
        session.add(trip)
        await session.flush()
        session.add(
            TripEtapa(
                etapa_id=etapa.id,
                trip_id=trip.id,
                func='mc',
                func_bordo='MC',
            )
        )
    await session.commit()

    response = await client.get(
        URL,
        params={'is_simulador': 'true'},
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == HTTPStatus.OK
    por_id = {m['missao_id']: m for m in response.json()['data']['missoes']}
    return por_id[recente.id]['trigramas']


async def test_trigramas_ult_promo_nulo_vem_antes_do_preenchido(
    client, token, session, pendencias
):
    """Mesmo posto: `ult_promo` nulo precede o preenchido (`nulls_first`).

    O preenchido tem menor id, trigrama alfabeticamente primeiro e e
    inserido antes; sem `nulls_first` o PG poe o nulo por ultimo.
    """
    _, _, recente, _ = pendencias

    trigramas = await _trigramas_ordenados(
        client,
        token,
        session,
        recente,
        [('AAB', date(2015, 1, 1), None), ('ZZY', None, None)],
    )

    assert trigramas == ['ZZY', 'AAB']


async def test_trigramas_ant_rel_nulo_conta_como_zero(
    client, token, session, pendencias
):
    """Mesma `ult_promo`: `ant_rel` nulo (= 0) precede `ant_rel=1`.

    O `ant_rel=1` tem menor id, trigrama alfabeticamente primeiro e e
    inserido antes; sem o `coalesce` o PG poe o nulo por ultimo.
    """
    _, _, recente, _ = pendencias

    trigramas = await _trigramas_ordenados(
        client,
        token,
        session,
        recente,
        [
            ('AAB', date(2015, 1, 1), 1),
            ('ZZY', date(2015, 1, 1), None),
        ],
    )

    assert trigramas == ['ZZY', 'AAB']
