"""Relatorio individual: funcao da etapa, deduplicacao e dono-ou-permissao."""

from datetime import date, datetime, time, timedelta
from http import HTTPStatus

import pytest
from sqlalchemy import select

from fcontrol_api.models.estatistica.esf_aer import EsforcoAereo
from fcontrol_api.models.estatistica.etapa import (
    Etapa,
    Missao,
    OIEtapa,
    TipoMissao,
    TripEtapa,
)
from fcontrol_api.models.security.resources import (
    Permissions,
    Resources,
    RolePermissions,
    Roles,
    UserRole,
)
from fcontrol_api.models.shared.aeronaves import Aeronave
from fcontrol_api.routers.estatistica.relatorio_anual import FUSO_LOCAL
from tests.api.fatbird.conftest import auth
from tests.factories import TripFactory, UserFactory

pytestmark = pytest.mark.anyio
ANO = 2025


def url(trip_id):
    return f'/estatistica/tripulantes/{trip_id}/relatorio-anual'


@pytest.fixture
async def refs(session):
    esf = EsforcoAereo(
        tipo='AVIAO',
        modelo='KC-390',
        grupo='COMPREP',
        prog='PRPO',
        sub_prog=None,
        aplicacao=None,
    )
    tipo = TipoMissao(cod='ADT', desc='Adestramento')
    session.add_all([
        esf,
        tipo,
        Aeronave(matricula='2870', active=True, sit='DI', obs=None),
        Aeronave(
            matricula='9970',
            active=True,
            sit='DI',
            obs=None,
            is_sim=True,
        ),
    ])
    await session.flush()
    return esf.id, tipo.id


async def etapa(
    session,
    refs,
    trip_id,
    *,
    funcoes=('lm',),
    ano=ANO,
    sim=False,
    org='11gt',
    regimes=(),
    data=None,
):
    missao = Missao(
        titulo='104',
        obs=None,
        uae=org,
        is_simulador=sim,
    )
    session.add(missao)
    await session.flush()
    voo = Etapa(
        missao_id=missao.id,
        obs=None,
        data=data or date(ano, 3, 10),
        origem='SBGL',
        destino='SBBR',
        dep=time(10),
        arr=time(12),
        anv='9970' if sim else '2870',
        pousos=2 if not sim else 0,
        tow=None,
        pax=None,
        carga=None,
        comb=None,
        lub=None,
        nivel=None,
        sagem=True,
        parte1=True,
    )
    session.add(voo)
    await session.flush()
    for func in funcoes:
        session.add(
            TripEtapa(
                etapa_id=voo.id,
                trip_id=trip_id,
                func=func,
                func_bordo='AC',
            )
        )
    esf_id, tipo_id = refs
    for reg, minutos in regimes:
        session.add(
            OIEtapa(
                etapa_id=voo.id,
                esf_aer_id=esf_id,
                tvoo=minutos,
                reg=reg,
                tipo_missao_id=tipo_id,
            )
        )
    await session.flush()


async def test_funcoes_da_etapa_independem_do_cadastro(
    client,
    session,
    trip_user,
    trip_token,
    refs,
):
    _, trip = trip_user
    trip.func = 'pil'
    await etapa(session, refs, trip.id, funcoes=('lm',))
    await etapa(session, refs, trip.id, funcoes=('ml',))
    await etapa(session, refs, trip.id, funcoes=('ml',), ano=ANO - 1)
    await session.commit()

    resp = await client.get(
        url(trip.id), params={'ano': ANO}, headers=auth(trip_token)
    )
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()['data']
    assert data['ano'] == ANO
    assert 'func' not in data['tripulante']
    assert data['tripulante']['id'] == trip.id
    real = data['aeronaves']
    assert real['total']['tvoo'] == 240
    assert real['total']['etapas'] == 2
    assert {r['func']: r['tvoo'] for r in real['por_funcao']} == {
        'lm': 120,
        'ml': 120,
    }
    assert {r['func'] for r in real['por_aeronave_funcao']} == {'lm', 'ml'}
    assert {r['modelo'] for r in real['por_aeronave_funcao']} == {'kc-390'}


async def test_multiplas_ois_e_funcoes_nao_multiplicam_total(
    client,
    session,
    trip_user,
    trip_token,
    refs,
):
    _, trip = trip_user
    await etapa(
        session,
        refs,
        trip.id,
        funcoes=('lm', 'lm', 'ml'),
        regimes=(('d', 60), ('n', 30), ('v', 30)),
    )
    await session.commit()
    resp = await client.get(
        url(trip.id), params={'ano': ANO}, headers=auth(trip_token)
    )
    assert resp.status_code == HTTPStatus.OK
    real = resp.json()['data']['aeronaves']
    assert real['total'] == {
        'tvoo': 120,
        'diurno': 60,
        'noturno': 30,
        'nvg': 30,
        'sem_regime': 0,
        'pousos': 2,
        'etapas': 1,
        'ultimo_voo': '2025-03-10',
    }
    assert {r['func']: r['tvoo'] for r in real['por_funcao']} == {
        'lm': 120,
        'ml': 120,
    }
    for row in real['por_funcao'] + real['por_aeronave_funcao']:
        assert row['noturno'] == 30
        assert row['nvg'] == 30
        assert row['sem_regime'] == 0


@pytest.mark.parametrize('sim', [False, True])
async def test_nvg_nao_compoe_noturno_nem_tempo_sem_regime(
    client, session, trip_user, trip_token, refs, sim
):
    _, trip = trip_user
    await etapa(session, refs, trip.id, sim=sim, regimes=(('v', 120),))
    await session.commit()
    response = await client.get(
        url(trip.id), params={'ano': ANO}, headers=auth(trip_token)
    )
    assert response.status_code == HTTPStatus.OK
    resumo = response.json()['data']['simuladores' if sim else 'aeronaves']
    for row in [
        resumo['total'],
        *resumo['por_funcao'],
        *resumo['por_aeronave_funcao'],
    ]:
        assert row['tvoo'] == 120
        assert row['diurno'] == 0
        assert row['noturno'] == 0
        assert row['nvg'] == 120
        assert row['sem_regime'] == 0


async def test_tempo_sem_regime_desconta_os_tres_regimes_independentes(
    client, session, trip_user, trip_token, refs
):
    _, trip = trip_user
    await etapa(
        session, refs, trip.id, regimes=(('d', 20), ('n', 30), ('v', 40))
    )
    await session.commit()
    response = await client.get(
        url(trip.id), params={'ano': ANO}, headers=auth(trip_token)
    )
    assert response.status_code == HTTPStatus.OK
    total = response.json()['data']['aeronaves']['total']
    assert total['tvoo'] == 120
    assert total['diurno'] == 20
    assert total['noturno'] == 30
    assert total['nvg'] == 40
    assert total['sem_regime'] == 30


async def test_simulador_e_etapas_sem_regime(
    client,
    session,
    trip_user,
    trip_token,
    refs,
):
    _, trip = trip_user
    await etapa(session, refs, trip.id)
    await etapa(session, refs, trip.id, sim=True, regimes=(('d', 120),))
    await session.commit()
    resp = await client.get(
        url(trip.id), params={'ano': ANO}, headers=auth(trip_token)
    )
    assert resp.status_code == HTTPStatus.OK
    data = resp.json()['data']
    assert data['aeronaves']['total']['tvoo'] == 120
    assert data['aeronaves']['total']['sem_regime'] == 120
    assert data['aeronaves']['total']['diurno'] == 0
    assert data['simuladores']['total']['tvoo'] == 120
    assert data['simuladores']['total']['diurno'] == 120


async def test_ano_sem_voos_devolve_resumo_zerado(
    client,
    trip_user,
    trip_token,
):
    _, trip = trip_user
    resp = await client.get(
        url(trip.id), params={'ano': ANO}, headers=auth(trip_token)
    )
    assert resp.status_code == HTTPStatus.OK
    for bloco in ('aeronaves', 'simuladores'):
        data = resp.json()['data'][bloco]
        assert data['total']['tvoo'] == 0
        assert data['total']['ultimo_voo'] is None
        assert data['por_funcao'] == []
        assert data['por_aeronave_funcao'] == []


async def test_tripulante_nao_consulta_relatorio_de_colega(
    client,
    outro_trip,
    trip_token,
):
    _, trip = outro_trip
    resp = await client.get(
        url(trip.id), params={'ano': ANO}, headers=auth(trip_token)
    )
    assert resp.status_code == HTTPStatus.FORBIDDEN


async def test_admin_consulta_tripulante_da_propria_org(
    client,
    trip_user,
    token,
):
    _, trip = trip_user
    resp = await client.get(
        url(trip.id), params={'ano': ANO}, headers=auth(token)
    )
    assert resp.status_code == HTTPStatus.OK


async def test_admin_nao_consulta_tripulante_de_outra_org(
    client,
    session,
    token,
):
    user = UserFactory(unidade='1gt')
    session.add(user)
    await session.flush()
    trip = TripFactory(user_id=user.id, uae='1gt')
    session.add(trip)
    await session.commit()
    resp = await client.get(
        url(trip.id), params={'ano': ANO}, headers=auth(token)
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND
    assert resp.json()['message'] == 'Tripulante não encontrado'


async def test_horas_de_missao_de_outra_org_nao_vazam(
    client,
    session,
    trip_user,
    trip_token,
    refs,
):
    _, trip = trip_user
    await etapa(session, refs, trip.id)
    await etapa(session, refs, trip.id, org='1gt')
    await session.commit()
    resp = await client.get(
        url(trip.id), params={'ano': ANO}, headers=auth(trip_token)
    )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['aeronaves']['total']['tvoo'] == 120


@pytest.mark.parametrize('ano', [2019, 10000])
async def test_ano_invalido(client, trip_user, trip_token, ano):
    _, trip = trip_user
    resp = await client.get(
        url(trip.id), params={'ano': ano}, headers=auth(trip_token)
    )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_sem_token(client, trip_user):
    _, trip = trip_user
    resp = await client.get(url(trip.id), params={'ano': ANO})
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.parametrize(
    ('org', 'status'),
    [
        ('11gt', HTTPStatus.OK),
        ('1gt', HTTPStatus.FORBIDDEN),
    ],
)
async def test_permissao_de_leitura_so_vale_na_org_ativa(
    client,
    session,
    trip_user,
    trip_token,
    outro_trip,
    org,
    status,
):
    user, _ = trip_user
    _, alvo = outro_trip
    recurso = await session.scalar(
        select(Resources).where(Resources.name == 'ops.tripulantes')
    )
    if recurso is None:
        recurso = Resources(name='ops.tripulantes', description='Tripulantes')
        session.add(recurso)
        await session.flush()
    permissao = Permissions(
        resource_id=recurso.id,
        name='view',
        description='Leitura',
    )
    role = Roles(name='leitor_relatorio', description='Leitura de tripulantes')
    session.add_all([permissao, role])
    await session.flush()
    session.add_all([
        RolePermissions(role_id=role.id, permission_id=permissao.id),
        UserRole(user_id=user.id, role_id=role.id, organizacao_id=org),
    ])
    alvo_id = alvo.id
    await session.commit()
    # O Role recem-criado tem permissions=[] no identity map. Recarregar
    # reproduz a sessao de uma requisicao real, com os grants persistidos.
    session.expire_all()
    resp = await client.get(
        url(alvo_id), params={'ano': ANO}, headers=auth(trip_token)
    )
    assert resp.status_code == status


async def test_ano_omitido_usa_ano_corrente(client, trip_user, trip_token):
    _, trip = trip_user
    resp = await client.get(url(trip.id), headers=auth(trip_token))
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['ano'] == date.today().year


async def test_etapa_futura_fica_fora_dos_totais_e_do_ultimo_voo(
    client, session, trip_user, trip_token, refs
):
    hoje = datetime.now(FUSO_LOCAL).date()
    futura = hoje + timedelta(days=1)
    if futura.year != hoje.year:
        pytest.skip('sem data futura possivel no ano corrente')
    passada = date(hoje.year, 1, 1)
    _, trip = trip_user
    await etapa(session, refs, trip.id, data=passada)
    await etapa(session, refs, trip.id, data=futura)
    await session.commit()
    resp = await client.get(
        url(trip.id), params={'ano': hoje.year}, headers=auth(trip_token)
    )
    assert resp.status_code == HTTPStatus.OK
    total = resp.json()['data']['aeronaves']['total']
    assert total['tvoo'] == 120
    assert total['etapas'] == 1
    assert total['ultimo_voo'] == passada.isoformat()


async def test_cadastro_sem_nome_completo_nao_impede_relatorio(
    client,
    session,
    trip_user,
    trip_token,
):
    user, trip = trip_user
    user.nome_completo = None
    await session.commit()
    resp = await client.get(url(trip.id), headers=auth(trip_token))
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()['data']['tripulante']['nome_completo'] is None


async def test_contexto_sistema_nao_le_relatorio(
    client,
    trip_user,
    token_sistema,
):
    _, trip = trip_user
    resp = await client.get(url(trip.id), headers=auth(token_sistema))
    assert resp.status_code == HTTPStatus.BAD_REQUEST


@pytest.mark.parametrize('trip_id', [0, 2_147_483_648])
async def test_id_fora_da_faixa(client, trip_token, trip_id):
    resp = await client.get(url(trip_id), headers=auth(trip_token))
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
