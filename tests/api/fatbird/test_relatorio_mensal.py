"""Relatorio mensal: calendario, historico e escopo da organizacao."""

from datetime import date, datetime, time, timedelta, timezone
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
from fcontrol_api.models.shared.funcoes import FuncaoUae
from tests.api.fatbird.conftest import auth
from tests.factories import TripFactory, UserFactory

pytestmark = pytest.mark.anyio
ANO = 2025
MES = 3


def url(trip_id):
    return f'/estatistica/tripulantes/{trip_id}/relatorio-mensal'


@pytest.fixture
def monthly_clock(monkeypatch):
    def congelar(instante):
        class DataRelatorio(datetime):
            @classmethod
            def now(cls, tz=None):
                return instante.astimezone(tz)

        monkeypatch.setattr(
            'fcontrol_api.routers.estatistica.relatorio_mensal.datetime',
            DataRelatorio,
        )

    congelar(datetime(2026, 3, 15, 15, tzinfo=timezone.utc))
    return congelar


@pytest.fixture
async def monthly_refs(session):
    esforco = EsforcoAereo(
        tipo='AVIAO',
        modelo='KC-390',
        grupo='COMPREP',
        prog='PRPO',
        sub_prog=None,
        aplicacao=None,
    )
    tipo = TipoMissao(cod='ADT', desc='Adestramento')
    session.add_all([
        esforco,
        tipo,
        Aeronave(matricula='2871', active=True, sit='DI', obs=None),
        Aeronave(
            matricula='9971', active=True, sit='DI', obs=None, is_sim=True
        ),
    ])
    await session.flush()
    return esforco.id, tipo.id


async def criar_etapa(
    session,
    refs,
    trip_id,
    *,
    data=date(ANO, MES, 10),
    funcoes=(('lm', 'AC'),),
    regimes=(),
    sim=False,
    org='11gt',
    anv=None,
    dep=time(10),
    arr=time(12),
    titulo='104',
):
    missao = Missao(titulo=titulo, obs=None, uae=org, is_simulador=sim)
    session.add(missao)
    await session.flush()
    voo = Etapa(
        missao_id=missao.id,
        obs=None,
        data=data,
        origem='SBGL',
        destino='SBBR',
        dep=dep,
        arr=arr,
        anv=anv or ('9971' if sim else '2871'),
        pousos=0 if sim else 2,
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
    for func, bordo in funcoes:
        session.add(
            TripEtapa(
                etapa_id=voo.id, trip_id=trip_id, func=func, func_bordo=bordo
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
    return voo


async def consultar(client, trip_id, token, *, ano=ANO, mes=MES):
    response = await client.get(
        url(trip_id), params={'ano': ano, 'mes': mes}, headers=auth(token)
    )
    assert response.status_code == HTTPStatus.OK
    return response.json()['data']


async def test_mes_separa_detalhes_e_acumulados_sem_incluir_mes_posterior(
    client,
    session,
    trip_user,
    trip_token,
    monthly_refs,
):
    _, trip = trip_user
    trip.func = 'pil'
    for data in (
        date(2024, 12, 31),
        date(2025, 1, 1),
        date(2025, 2, 28),
        date(2025, 3, 1),
        date(2025, 3, 31),
        date(2025, 4, 1),
    ):
        await criar_etapa(session, monthly_refs, trip.id, data=data)
    await session.commit()

    report = await consultar(client, trip.id, trip_token)
    assert report['ano'] == ANO
    assert report['mes'] == MES
    assert report['tripulante']['id'] == trip.id
    assert 'func' not in report['tripulante']
    real = report['aeronaves']
    assert real['total']['tvoo'] == 240
    assert real['total']['etapas'] == 2
    assert real['total']['ultimo_voo'] == '2025-03-31'
    assert real['acumulado_ano']['tvoo'] == 480
    assert real['acumulado_ano']['etapas'] == 4
    assert real['acumulado_geral']['tvoo'] == 600
    assert real['acumulado_geral']['etapas'] == 5
    assert real['acumulado_geral']['ultimo_voo'] == '2025-03-31'
    assert [row['data'] for row in real['etapas']] == [
        '2025-03-01',
        '2025-03-31',
    ]
    assert [
        (row['modelo'], row['func'], row['tvoo'])
        for row in real['por_aeronave_funcao']
    ] == [('kc-390', 'lm', 240)]


async def test_ois_e_funcoes_legadas_nao_duplicam_etapa_ou_horas(
    client,
    session,
    trip_user,
    trip_token,
    monthly_refs,
):
    _, trip = trip_user
    voo = await criar_etapa(
        session,
        monthly_refs,
        trip.id,
        funcoes=(('lm', 'AC'), ('lm', 'AC'), ('lm', 'IN'), ('ml', 'AC')),
        regimes=(('d', 60), ('n', 30), ('v', 30)),
    )
    await session.commit()
    report = await consultar(client, trip.id, trip_token)
    real = report['aeronaves']
    expected = {
        'tvoo': 120,
        'diurno': 60,
        'noturno': 30,
        'nvg': 30,
        'sem_regime': 0,
        'pousos': 2,
        'etapas': 1,
        'ultimo_voo': '2025-03-10',
    }
    for key in ('total', 'acumulado_ano', 'acumulado_geral'):
        assert real[key] == expected
    assert {
        row['func']: row['tvoo'] for row in real['por_aeronave_funcao']
    } == {'lm': 120, 'ml': 120}
    assert len(real['etapas']) == 1
    row = real['etapas'][0]
    assert row['id'] == voo.id
    assert row['missao_id'] == voo.missao_id
    assert row['missao'] == '104'
    assert row['anv'] == '2871'
    assert row['modelo'] == 'kc-390'
    assert row['origem'] == 'SBGL'
    assert row['destino'] == 'SBBR'
    assert row['dep'] == '10:00:00'
    assert row['arr'] == '12:00:00'
    for key in ('tvoo', 'diurno', 'noturno', 'nvg', 'sem_regime', 'pousos'):
        assert row[key] == expected[key]
    assert {(func['func'], func['func_bordo']) for func in row['funcoes']} == {
        ('lm', 'AC'),
        ('lm', 'IN'),
        ('ml', 'AC'),
    }
    assert len(row['funcoes']) == 3
    assert all(func['nome'] for func in row['funcoes'])


@pytest.mark.parametrize('sim', [False, True])
async def test_nvg_independente_e_etapa_sem_oi(
    client,
    session,
    trip_user,
    trip_token,
    monthly_refs,
    sim,
):
    _, trip = trip_user
    await criar_etapa(
        session, monthly_refs, trip.id, sim=sim, regimes=(('v', 120),)
    )
    await criar_etapa(
        session, monthly_refs, trip.id, sim=sim, data=date(ANO, MES, 11)
    )
    await session.commit()
    report = await consultar(client, trip.id, trip_token)
    block = report['simuladores' if sim else 'aeronaves']
    for key in ('total', 'acumulado_ano', 'acumulado_geral'):
        assert block[key]['tvoo'] == 240
        assert block[key]['noturno'] == 0
        assert block[key]['nvg'] == 120
        assert block[key]['sem_regime'] == 120
    assert block['etapas'][0]['nvg'] == 120
    assert block['etapas'][0]['noturno'] == 0
    assert block['etapas'][1]['sem_regime'] == 120
    assert block['por_aeronave_funcao'][0]['nvg'] == 120
    assert block['por_aeronave_funcao'][0]['noturno'] == 0


async def test_missao_define_simulador_e_nao_cadastro_da_aeronave(
    client,
    session,
    trip_user,
    trip_token,
    monthly_refs,
):
    _, trip = trip_user
    await criar_etapa(session, monthly_refs, trip.id, sim=True, anv='2871')
    await criar_etapa(session, monthly_refs, trip.id, sim=False, anv='9971')
    await session.commit()
    report = await consultar(client, trip.id, trip_token)
    assert report['simuladores']['total']['tvoo'] == 120
    assert report['aeronaves']['total']['tvoo'] == 120
    assert report['simuladores']['etapas'][0]['anv'] == '2871'
    assert report['aeronaves']['etapas'][0]['anv'] == '9971'


async def test_detalhes_ordenados_por_data_decolagem_e_id(
    client,
    session,
    trip_user,
    trip_token,
    monthly_refs,
):
    _, trip = trip_user
    tarde = await criar_etapa(
        session, monthly_refs, trip.id, dep=time(14), arr=time(16)
    )
    cedo1 = await criar_etapa(session, monthly_refs, trip.id)
    anterior = await criar_etapa(
        session, monthly_refs, trip.id, data=date(ANO, MES, 9)
    )
    cedo2 = await criar_etapa(session, monthly_refs, trip.id)
    await session.commit()
    report = await consultar(client, trip.id, trip_token)
    assert [row['id'] for row in report['aeronaves']['etapas']] == [
        anterior.id,
        cedo1.id,
        cedo2.id,
        tarde.id,
    ]


@pytest.mark.parametrize(
    ('ano', 'mes', 'ultimo_dia'),
    [
        (2024, 2, 29),
        (2025, 2, 28),
        (2024, 12, 31),
    ],
)
async def test_fim_do_mes_e_virada_do_ano(
    client,
    session,
    trip_user,
    trip_token,
    monthly_refs,
    ano,
    mes,
    ultimo_dia,
):
    _, trip = trip_user
    fim = date(ano, mes, ultimo_dia)
    await criar_etapa(session, monthly_refs, trip.id, data=fim)
    await criar_etapa(
        session, monthly_refs, trip.id, data=fim + timedelta(days=1)
    )
    await session.commit()
    report = await consultar(client, trip.id, trip_token, ano=ano, mes=mes)
    real = report['aeronaves']
    assert [row['data'] for row in real['etapas']] == [fim.isoformat()]
    for key in ('total', 'acumulado_ano', 'acumulado_geral'):
        assert real[key]['tvoo'] == 120
        assert real[key]['ultimo_voo'] == fim.isoformat()


async def test_mes_sem_voos_preserva_acumulados_anteriores(
    client,
    session,
    trip_user,
    trip_token,
    monthly_refs,
):
    _, trip = trip_user
    await criar_etapa(session, monthly_refs, trip.id, data=date(2024, 12, 31))
    await criar_etapa(session, monthly_refs, trip.id, data=date(2025, 2, 28))
    await session.commit()
    report = await consultar(client, trip.id, trip_token)
    real = report['aeronaves']
    assert real['total']['tvoo'] == 0
    assert real['total']['ultimo_voo'] is None
    assert real['etapas'] == []
    assert real['por_aeronave_funcao'] == []
    assert real['acumulado_ano']['tvoo'] == 120
    assert real['acumulado_geral']['tvoo'] == 240
    assert real['acumulado_geral']['ultimo_voo'] == '2025-02-28'


async def test_voos_futuros_nao_compoem_relatorio_ou_acumulados(
    client,
    session,
    trip_user,
    trip_token,
    monthly_refs,
    monthly_clock,
):
    _, trip = trip_user
    hoje = date(2026, 3, 15)
    futura = hoje + timedelta(days=1)
    await criar_etapa(session, monthly_refs, trip.id, data=hoje)
    await criar_etapa(session, monthly_refs, trip.id, data=futura)
    await session.commit()
    report = await consultar(
        client, trip.id, trip_token, ano=futura.year, mes=futura.month
    )
    real = report['aeronaves']
    assert real['acumulado_geral']['tvoo'] == 120
    assert real['acumulado_geral']['ultimo_voo'] == hoje.isoformat()
    assert all(row['data'] <= hoje.isoformat() for row in real['etapas'])


async def test_horas_de_missao_de_outra_org_nao_vazam_em_nenhum_acumulado(
    client,
    session,
    trip_user,
    trip_token,
    monthly_refs,
):
    _, trip = trip_user
    await criar_etapa(session, monthly_refs, trip.id)
    for data in (date(2024, 12, 31), date(2025, 2, 1), date(2025, 3, 10)):
        await criar_etapa(session, monthly_refs, trip.id, org='1gt', data=data)
    await session.commit()
    report = await consultar(client, trip.id, trip_token)
    real = report['aeronaves']
    for key in ('total', 'acumulado_ano', 'acumulado_geral'):
        assert real[key]['tvoo'] == 120
    assert len(real['etapas']) == 1


async def test_tripulante_nao_consulta_colega(client, outro_trip, trip_token):
    _, trip = outro_trip
    response = await client.get(url(trip.id), headers=auth(trip_token))
    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_admin_consulta_historico_de_tripulante_inativo_sem_nome(
    client,
    session,
    trip_user,
    token,
):
    user, trip = trip_user
    user.nome_completo = None
    user.active = False
    trip.active = False
    await session.commit()
    report = await consultar(client, trip.id, token)
    assert report['tripulante']['nome_completo'] is None
    assert report['tripulante']['id'] == trip.id
    assert report['aeronaves']['total']['tvoo'] == 0


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
    response = await client.get(url(trip.id), headers=auth(token))
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()['message'] == 'Tripulante não encontrado'


@pytest.mark.parametrize(
    ('org', 'status'),
    [
        ('11gt', HTTPStatus.OK),
        ('1gt', HTTPStatus.FORBIDDEN),
    ],
)
async def test_leitura_sem_admin_so_vale_na_org_da_permissao(
    client,
    session,
    trip_user,
    trip_token,
    outro_trip,
    org,
    status,
):
    user, _ = trip_user
    _, trip = outro_trip
    recurso = await session.scalar(
        select(Resources).where(Resources.name == 'ops.tripulantes')
    )
    if recurso is None:
        recurso = Resources(name='ops.tripulantes', description='Tripulantes')
        session.add(recurso)
        await session.flush()
    permissao = Permissions(
        resource_id=recurso.id, name='view', description='Leitura'
    )
    role = Roles(name='leitor_mensal', description='Leitura de tripulantes')
    session.add_all([permissao, role])
    await session.flush()
    session.add_all([
        RolePermissions(role_id=role.id, permission_id=permissao.id),
        UserRole(user_id=user.id, role_id=role.id, organizacao_id=org),
    ])
    alvo_id = trip.id
    await session.commit()
    session.expire_all()
    response = await client.get(url(alvo_id), headers=auth(trip_token))
    assert response.status_code == status


@pytest.mark.parametrize(
    'params',
    [
        {'mes': 0},
        {'mes': 13},
        {'ano': 2019},
        {'ano': 10000},
    ],
)
async def test_periodo_invalido(client, trip_user, trip_token, params):
    _, trip = trip_user
    response = await client.get(
        url(trip.id), params=params, headers=auth(trip_token)
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.parametrize('trip_id', [0, 2_147_483_648])
async def test_trip_id_fora_da_faixa(client, trip_token, trip_id):
    response = await client.get(url(trip_id), headers=auth(trip_token))
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_sem_token(client, trip_user):
    _, trip = trip_user
    response = await client.get(url(trip.id))
    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_sem_org_ativa(client, trip_user, token_sistema):
    _, trip = trip_user
    response = await client.get(url(trip.id), headers=auth(token_sistema))
    assert response.status_code == HTTPStatus.BAD_REQUEST


async def test_defaults_ano_e_mes_locais(
    client, trip_user, trip_token, monthly_clock
):
    _, trip = trip_user
    # UTC ja virou janeiro, mas o calendario local ainda e dezembro.
    monthly_clock(datetime(2026, 1, 1, 2, tzinfo=timezone.utc))
    response = await client.get(url(trip.id), headers=auth(trip_token))
    assert response.status_code == HTTPStatus.OK
    report = response.json()['data']
    assert report['ano'] == 2025
    assert report['mes'] == 12


async def test_mes_futuro_vazio_mantem_historico_ate_hoje(
    client, session, trip_user, trip_token, monthly_refs, monthly_clock
):
    _, trip = trip_user
    await criar_etapa(session, monthly_refs, trip.id, data=date(2026, 3, 15))
    await criar_etapa(session, monthly_refs, trip.id, data=date(2026, 4, 1))
    await session.commit()
    report = await consultar(client, trip.id, trip_token, ano=2026, mes=4)
    real = report['aeronaves']
    assert real['total']['tvoo'] == 0
    assert real['etapas'] == []
    assert real['por_aeronave_funcao'] == []
    assert real['acumulado_ano']['tvoo'] == 120
    assert real['acumulado_geral']['tvoo'] == 120
    assert real['acumulado_geral']['ultimo_voo'] == '2026-03-15'


async def test_ano_maximo_sem_overflow_e_geral_inclui_legado_anterior_a_2020(
    client, session, trip_user, trip_token, monthly_refs, monthly_clock
):
    _, trip = trip_user
    await criar_etapa(session, monthly_refs, trip.id, data=date(2019, 12, 31))
    await session.commit()
    report = await consultar(client, trip.id, trip_token, ano=9999, mes=12)
    real = report['aeronaves']
    assert real['total']['tvoo'] == 0
    assert real['acumulado_ano']['tvoo'] == 0
    assert real['acumulado_geral']['tvoo'] == 120
    assert real['acumulado_geral']['ultimo_voo'] == '2019-12-31'


async def test_nome_customizado_local_e_funcao_legada_sem_catalogo(
    client, session, trip_user, trip_token, monthly_refs
):
    _, trip = trip_user
    local = await session.scalar(
        select(FuncaoUae).where(
            FuncaoUae.uae == '11gt', FuncaoUae.func_cod == 'lm'
        )
    )
    local.nome_custom = 'Mestre de cargas local'
    outra = await session.scalar(
        select(FuncaoUae).where(
            FuncaoUae.uae == '1gt', FuncaoUae.func_cod == 'lm'
        )
    )
    outra.nome_custom = 'Nome de outra unidade'
    await criar_etapa(
        session,
        monthly_refs,
        trip.id,
        funcoes=(('lm', 'AC'), ('zzz', 'AC')),
        titulo=None,
    )
    await session.commit()
    report = await consultar(client, trip.id, trip_token)
    real = report['aeronaves']
    expected = {'lm': 'Mestre de cargas local', 'zzz': 'zzz'}
    assert {
        func['func']: func['nome'] for func in real['etapas'][0]['funcoes']
    } == expected
    assert {
        row['func']: row['nome'] for row in real['por_aeronave_funcao']
    } == expected
    assert real['etapas'][0]['missao'] is None
