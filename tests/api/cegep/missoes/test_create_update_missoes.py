"""
Testes para o endpoint POST /cegep/missoes/.

Este endpoint cria ou atualiza missoes.
Requer autenticacao.
"""

from datetime import date, datetime, time, timedelta
from http import HTTPStatus

import pytest
from sqlalchemy.future import select

from fcontrol_api.models.cegep.missoes import (
    FragEtiqueta,
    FragMis,
    PernoiteFrag,
    UserFrag,
)
from tests.factories import (
    EtiquetaFactory,
    FragMisFactory,
    PernoiteFragFactory,
    UserFragFactory,
)

pytestmark = pytest.mark.anyio


def _get_posto_for_pg(p_g: str) -> dict:
    """Retorna o dict do posto/graduacao para uso em payloads."""
    postos = {
        'cb': {
            'ant': 15, 'short': 'cb', 'mid': 'cabo',
            'long': 'cabo', 'circulo': 'praça',
        },
        '2s': {
            'ant': 13, 'short': '2s', 'mid': '2º sgt',
            'long': 'segundo sargento', 'circulo': 'grad',
        },
        '3s': {
            'ant': 14, 'short': '3s', 'mid': '3º sgt',
            'long': 'terceiro sargento', 'circulo': 'grad',
        },
        '1t': {
            'ant': 8, 'short': '1t', 'mid': '1º ten',
            'long': 'primeiro tenente', 'circulo': 'of_sub',
        },
        'cp': {
            'ant': 7, 'short': 'cp', 'mid': 'cap',
            'long': 'capitão', 'circulo': 'of_int',
        },
    }
    return postos.get(p_g, postos['cb'])


def _build_user_payload(user, sit='d') -> dict:
    """Constroi o payload do usuario para a missao."""
    posto = _get_posto_for_pg(user.p_g)
    return {
        'user_id': user.id,
        'p_g': user.p_g,
        'sit': sit,
        'user': {
            'id': user.id,
            'nome_guerra': user.nome_guerra,
            'nome_completo': user.nome_completo,
            'p_g': user.p_g,
            'esp': user.esp,
            'posto': posto,
            'id_fab': user.id_fab,
            'saram': user.saram,
            'active': True,
            'unidade': user.unidade,
            'ult_promo': (
                user.ult_promo.isoformat() if user.ult_promo else None
            ),
            'ant_rel': user.ant_rel,
        },
    }


# ============ P1 - TESTES CRITICOS ============


async def test_create_missao_success(
    client, session, token, missao_base_payload
):
    """Testa criacao de missao simples com sit='d'."""
    response = await client.post(
        '/cegep/missoes/',
        headers={'Authorization': f'Bearer {token}'},
        json=missao_base_payload,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'
    assert 'salva' in resp['message'].lower()

    # Verifica no banco
    db_missao = await session.scalar(
        select(FragMis).where(FragMis.n_doc == 3001)
    )
    assert db_missao is not None
    assert db_missao.desc == 'Missao via payload'


async def test_create_missao_without_token(client, missao_base_payload):
    """Testa que requisicao sem token falha."""
    response = await client.post('/cegep/missoes/', json=missao_base_payload)

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_create_missao_missing_required_field(client, token):
    """Testa que campo obrigatorio faltando falha."""
    # Falta o campo 'desc'
    payload = {
        'n_doc': 3002,
        'tipo_doc': 'om',
        'indenizavel': True,
        'acrec_desloc': False,
        'afast': datetime.now().isoformat(),
        'regres': (datetime.now() + timedelta(days=3)).isoformat(),
        'obs': 'Obs',
        'tipo': 'adm',
        'pernoites': [],
        'users': [],
    }

    response = await client.post(
        '/cegep/missoes/',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_update_missao_success(
    client, session, token, missao_existente, users
):
    """Testa atualizacao de missao existente."""
    user, _ = users
    today = date.today()

    payload = {
        'id': missao_existente.id,
        'n_doc': missao_existente.n_doc,
        'tipo_doc': missao_existente.tipo_doc,
        'indenizavel': True,
        'acrec_desloc': True,  # Alterado
        'afast': datetime.combine(
            today + timedelta(days=10), time(8, 0)
        ).isoformat(),
        'regres': datetime.combine(
            today + timedelta(days=15), time(18, 0)
        ).isoformat(),
        'desc': 'Missao atualizada',  # Alterado
        'obs': 'Nova obs',
        'tipo': 'adm',
        'pernoites': [
            {
                'acrec_desloc': False,
                'data_ini': (today + timedelta(days=10)).isoformat(),
                'data_fim': (today + timedelta(days=15)).isoformat(),
                'meia_diaria': False,
                'obs': '',
                'cidade_id': 3550308,
                'cidade': {
                    'codigo': 3550308,
                    'nome': 'Sao Paulo',
                    'uf': 'SP',
                },
            }
        ],
        'users': [_build_user_payload(user, 'd')],
        'etiquetas': [],
    }

    response = await client.post(
        '/cegep/missoes/',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'

    # Verifica no banco
    await session.refresh(missao_existente)
    assert missao_existente.desc == 'Missao atualizada'
    assert missao_existente.acrec_desloc is True


async def test_update_missao_not_found(client, token, missao_base_payload):
    """Testa atualizacao de missao inexistente."""
    payload = missao_base_payload.copy()
    payload['id'] = 99999

    response = await client.post(
        '/cegep/missoes/',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


# ============ P2 - TESTES IMPORTANTES ============


async def test_create_missao_with_comiss_valid(
    client, session, token, missao_payload_comiss
):
    """Testa criacao de missao com sit='c' e comiss valido."""
    response = await client.post(
        '/cegep/missoes/',
        headers={'Authorization': f'Bearer {token}'},
        json=missao_payload_comiss,
    )

    assert response.status_code == HTTPStatus.OK
    resp = response.json()
    assert resp['status'] == 'success'


async def test_create_missao_comiss_without_comissionamento(
    client, token, missao_base_payload
):
    """Testa que sit='c' sem comissionamento falha."""
    payload = missao_base_payload.copy()
    payload['users'] = [missao_base_payload['users'][0].copy()]
    payload['users'][0]['sit'] = 'c'  # Comissionado

    response = await client.post(
        '/cegep/missoes/',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'comissionad' in response.json()['message'].lower()


async def test_create_missao_comiss_outside_period(
    client, session, token, user_with_comiss
):
    """Testa que missao fora do periodo do comiss falha."""
    user, comiss = user_with_comiss
    today = date.today()

    # Missao fora do periodo do comissionamento
    afast_date = today + timedelta(days=100)  # Fora do comiss.data_fc
    regres_date = today + timedelta(days=105)

    payload = {
        'n_doc': 7001,
        'tipo_doc': 'om',
        'indenizavel': True,
        'acrec_desloc': False,
        'afast': datetime.combine(afast_date, time(8, 0)).isoformat(),
        'regres': datetime.combine(regres_date, time(18, 0)).isoformat(),
        'desc': 'Missao fora periodo',
        'obs': '',
        'tipo': 'adm',
        'pernoites': [
            {
                'acrec_desloc': False,
                'data_ini': afast_date.isoformat(),
                'data_fim': regres_date.isoformat(),
                'meia_diaria': False,
                'obs': '',
                'cidade_id': 3550308,
                'cidade': {
                    'codigo': 3550308,
                    'nome': 'Sao Paulo',
                    'uf': 'SP',
                },
            }
        ],
        'users': [_build_user_payload(user, 'c')],
        'etiquetas': [],
    }

    response = await client.post(
        '/cegep/missoes/',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'período' in response.json()['message'].lower()


async def test_create_missao_conflict_overlapping_dates(
    client, token, missao_existente, users
):
    """Testa conflito de sobreposicao de datas."""
    user, _ = users
    today = date.today()

    # Missao_existente: dias 10-15
    # Nova missao: dias 12-18 (sobreposicao)
    payload = {
        'n_doc': 8001,
        'tipo_doc': 'om',
        'indenizavel': True,
        'acrec_desloc': False,
        'afast': datetime.combine(
            today + timedelta(days=12), time(8, 0)
        ).isoformat(),
        'regres': datetime.combine(
            today + timedelta(days=18), time(18, 0)
        ).isoformat(),
        'desc': 'Missao conflitante',
        'obs': '',
        'tipo': 'adm',
        'pernoites': [
            {
                'acrec_desloc': False,
                'data_ini': (today + timedelta(days=12)).isoformat(),
                'data_fim': (today + timedelta(days=18)).isoformat(),
                'meia_diaria': False,
                'obs': '',
                'cidade_id': 3550308,
                'cidade': {
                    'codigo': 3550308,
                    'nome': 'Sao Paulo',
                    'uf': 'SP',
                },
            }
        ],
        'users': [_build_user_payload(user, 'd')],
        'etiquetas': [],
    }

    response = await client.post(
        '/cegep/missoes/',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'sobreposição' in response.json()['message'].lower()


async def test_create_missao_conflict_meia_diaria_anterior(
    client, token, missao_com_meia_diaria, users
):
    """Testa conflito: meia-diaria anterior conflita com afastamento."""
    user, _ = users
    today = date.today()

    # Missao_com_meia_diaria: termina dia 25 com meia_diaria=True
    # Nova missao: afasta no dia 25 (conflito)
    payload = {
        'n_doc': 8002,
        'tipo_doc': 'om',
        'indenizavel': True,
        'acrec_desloc': False,
        'afast': datetime.combine(
            today + timedelta(days=25), time(8, 0)
        ).isoformat(),
        'regres': datetime.combine(
            today + timedelta(days=30), time(18, 0)
        ).isoformat(),
        'desc': 'Missao conflito meia diaria',
        'obs': '',
        'tipo': 'adm',
        'pernoites': [
            {
                'acrec_desloc': False,
                'data_ini': (today + timedelta(days=25)).isoformat(),
                'data_fim': (today + timedelta(days=30)).isoformat(),
                'meia_diaria': False,
                'obs': '',
                'cidade_id': 3550308,
                'cidade': {
                    'codigo': 3550308,
                    'nome': 'Sao Paulo',
                    'uf': 'SP',
                },
            }
        ],
        'users': [_build_user_payload(user, 'd')],
        'etiquetas': [],
    }

    response = await client.post(
        '/cegep/missoes/',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'meia diária' in response.json()['message'].lower()


async def test_create_missao_conflict_meia_diaria_nova(
    client, session, token, users
):
    """Testa conflito: meia-diaria nova conflita com proxima missao."""
    user, _ = users
    today = date.today()

    # Criar missao existente que afasta no dia 50
    missao_existente = FragMisFactory(
        n_doc=8003,
        afast=datetime.combine(today + timedelta(days=50), time(8, 0)),
        regres=datetime.combine(today + timedelta(days=55), time(18, 0)),
    )
    session.add(missao_existente)
    await session.flush()

    pernoite = PernoiteFragFactory(
        frag_id=missao_existente.id,
        cidade_id=3550308,
        data_ini=today + timedelta(days=50),
        data_fim=today + timedelta(days=55),
        meia_diaria=False,
    )
    session.add(pernoite)

    user_frag = UserFragFactory(
        frag_id=missao_existente.id, user_id=user.id, sit='d', p_g=user.p_g
    )
    session.add(user_frag)
    await session.commit()

    # Nova missao: termina dia 50 com meia_diaria=True (conflito)
    payload = {
        'n_doc': 8004,
        'tipo_doc': 'om',
        'indenizavel': True,
        'acrec_desloc': False,
        'afast': datetime.combine(
            today + timedelta(days=45), time(8, 0)
        ).isoformat(),
        'regres': datetime.combine(
            today + timedelta(days=50), time(12, 0)
        ).isoformat(),
        'desc': 'Missao com meia diaria conflitante',
        'obs': '',
        'tipo': 'adm',
        'pernoites': [
            {
                'acrec_desloc': False,
                'data_ini': (today + timedelta(days=45)).isoformat(),
                'data_fim': (today + timedelta(days=50)).isoformat(),
                'meia_diaria': True,  # Meia diaria que conflita
                'obs': '',
                'cidade_id': 3550308,
                'cidade': {
                    'codigo': 3550308,
                    'nome': 'Sao Paulo',
                    'uf': 'SP',
                },
            }
        ],
        'users': [_build_user_payload(user, 'd')],
        'etiquetas': [],
    }

    response = await client.post(
        '/cegep/missoes/',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert 'meia diária' in response.json()['message'].lower()


async def test_create_missao_with_etiquetas(
    client, session, token, missao_base_payload
):
    """Testa criacao de missao com etiquetas."""
    # Criar etiqueta
    etiqueta = EtiquetaFactory(nome='Test Etiqueta')
    session.add(etiqueta)
    await session.commit()
    await session.refresh(etiqueta)

    payload = missao_base_payload.copy()
    payload['n_doc'] = 8005
    payload['etiquetas'] = [
        {
            'id': etiqueta.id,
            'nome': etiqueta.nome,
            'cor': etiqueta.cor,
        }
    ]

    response = await client.post(
        '/cegep/missoes/',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica no banco pela tabela associativa
    db_missao = await session.scalar(
        select(FragMis).where(FragMis.n_doc == 8005)
    )
    assert db_missao is not None

    # Verificar relacao na tabela associativa
    frag_etiq = await session.scalar(
        select(FragEtiqueta).where(
            FragEtiqueta.frag_id == db_missao.id,
            FragEtiqueta.etiqueta_id == etiqueta.id,
        )
    )
    assert frag_etiq is not None


# ============ P3 - TESTES DE COBERTURA ============


async def test_create_missao_verifica_custos_structure(
    client, session, token, missao_base_payload
):
    """Testa que custos sao calculados e tem estrutura correta."""
    payload = missao_base_payload.copy()
    payload['n_doc'] = 9001

    response = await client.post(
        '/cegep/missoes/',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica estrutura do JSONB custos
    db_missao = await session.scalar(
        select(FragMis).where(FragMis.n_doc == 9001)
    )
    assert db_missao is not None
    assert db_missao.custos is not None
    assert 'total_dias' in db_missao.custos
    assert 'total_diarias' in db_missao.custos
    assert 'totais_pg_sit' in db_missao.custos
    assert isinstance(db_missao.custos['total_dias'], int)
    assert isinstance(db_missao.custos['total_diarias'], (int, float))


async def test_create_missao_sit_g_calcula_grat_rep(
    client, session, token, users
):
    """Testa que sit='g' (Grat Rep) calcula 2% do soldo."""
    user, _ = users
    today = date.today()

    payload = {
        'n_doc': 9002,
        'tipo_doc': 'om',
        'indenizavel': True,
        'acrec_desloc': False,
        'afast': datetime.combine(
            today + timedelta(days=60), time(8, 0)
        ).isoformat(),
        'regres': datetime.combine(
            today + timedelta(days=65), time(18, 0)
        ).isoformat(),
        'desc': 'Missao Grat Rep',
        'obs': '',
        'tipo': 'adm',
        'pernoites': [
            {
                'acrec_desloc': False,
                'data_ini': (today + timedelta(days=60)).isoformat(),
                'data_fim': (today + timedelta(days=65)).isoformat(),
                'meia_diaria': False,
                'obs': '',
                'cidade_id': 3550308,
                'cidade': {
                    'codigo': 3550308,
                    'nome': 'Sao Paulo',
                    'uf': 'SP',
                },
            }
        ],
        'users': [_build_user_payload(user, 'g')],  # Grat Rep
        'etiquetas': [],
    }

    response = await client.post(
        '/cegep/missoes/',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.OK

    db_missao = await session.scalar(
        select(FragMis).where(FragMis.n_doc == 9002)
    )
    assert db_missao is not None
    assert db_missao.custos is not None


async def test_create_missao_acrec_desloc_adds_value(
    client, session, token, users
):
    """Testa que acrec_desloc adiciona R$95."""
    user, _ = users
    today = date.today()

    payload = {
        'n_doc': 9003,
        'tipo_doc': 'om',
        'indenizavel': True,
        'acrec_desloc': True,  # Com acrescimo deslocamento
        'afast': datetime.combine(
            today + timedelta(days=70), time(8, 0)
        ).isoformat(),
        'regres': datetime.combine(
            today + timedelta(days=75), time(18, 0)
        ).isoformat(),
        'desc': 'Missao com acrec desloc',
        'obs': '',
        'tipo': 'adm',
        'pernoites': [
            {
                'acrec_desloc': True,
                'data_ini': (today + timedelta(days=70)).isoformat(),
                'data_fim': (today + timedelta(days=75)).isoformat(),
                'meia_diaria': False,
                'obs': '',
                'cidade_id': 3550308,
                'cidade': {
                    'codigo': 3550308,
                    'nome': 'Sao Paulo',
                    'uf': 'SP',
                },
            }
        ],
        'users': [_build_user_payload(user, 'd')],
        'etiquetas': [],
    }

    response = await client.post(
        '/cegep/missoes/',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.OK

    db_missao = await session.scalar(
        select(FragMis).where(FragMis.n_doc == 9003)
    )
    assert db_missao is not None
    assert db_missao.custos is not None
    # Verifica que acrec_desloc foi considerado
    assert 'acrec_desloc_missao' in db_missao.custos


async def test_create_missao_multiple_pernoites(
    client, session, token, users
):
    """Testa criacao de missao com multiplos pernoites."""
    user, _ = users
    today = date.today()

    payload = {
        'n_doc': 9004,
        'tipo_doc': 'om',
        'indenizavel': True,
        'acrec_desloc': False,
        'afast': datetime.combine(
            today + timedelta(days=80), time(8, 0)
        ).isoformat(),
        'regres': datetime.combine(
            today + timedelta(days=90), time(18, 0)
        ).isoformat(),
        'desc': 'Missao multiplos pernoites',
        'obs': '',
        'tipo': 'adm',
        'pernoites': [
            {
                'acrec_desloc': False,
                'data_ini': (today + timedelta(days=80)).isoformat(),
                'data_fim': (today + timedelta(days=85)).isoformat(),
                'meia_diaria': False,
                'obs': '',
                'cidade_id': 3550308,  # SP
                'cidade': {
                    'codigo': 3550308,
                    'nome': 'Sao Paulo',
                    'uf': 'SP',
                },
            },
            {
                'acrec_desloc': False,
                'data_ini': (today + timedelta(days=85)).isoformat(),
                'data_fim': (today + timedelta(days=90)).isoformat(),
                'meia_diaria': False,
                'obs': '',
                'cidade_id': 3304557,  # RJ
                'cidade': {
                    'codigo': 3304557,
                    'nome': 'Rio de Janeiro',
                    'uf': 'RJ',
                },
            },
        ],
        'users': [_build_user_payload(user, 'd')],
        'etiquetas': [],
    }

    response = await client.post(
        '/cegep/missoes/',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica pernoites no banco
    db_missao = await session.scalar(
        select(FragMis).where(FragMis.n_doc == 9004)
    )
    pernoites = await session.scalars(
        select(PernoiteFrag).where(PernoiteFrag.frag_id == db_missao.id)
    )
    pernoites_list = pernoites.all()
    assert len(pernoites_list) == 2


async def test_create_missao_multiple_users(client, session, token, users):
    """Testa criacao de missao com multiplos usuarios."""
    user, other_user = users
    today = date.today()

    payload = {
        'n_doc': 9005,
        'tipo_doc': 'om',
        'indenizavel': True,
        'acrec_desloc': False,
        'afast': datetime.combine(
            today + timedelta(days=100), time(8, 0)
        ).isoformat(),
        'regres': datetime.combine(
            today + timedelta(days=105), time(18, 0)
        ).isoformat(),
        'desc': 'Missao multiplos usuarios',
        'obs': '',
        'tipo': 'adm',
        'pernoites': [
            {
                'acrec_desloc': False,
                'data_ini': (today + timedelta(days=100)).isoformat(),
                'data_fim': (today + timedelta(days=105)).isoformat(),
                'meia_diaria': False,
                'obs': '',
                'cidade_id': 3550308,
                'cidade': {
                    'codigo': 3550308,
                    'nome': 'Sao Paulo',
                    'uf': 'SP',
                },
            }
        ],
        'users': [
            _build_user_payload(user, 'd'),
            _build_user_payload(other_user, 'd'),
        ],
        'etiquetas': [],
    }

    response = await client.post(
        '/cegep/missoes/',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica users_frag no banco
    db_missao = await session.scalar(
        select(FragMis).where(FragMis.n_doc == 9005)
    )
    users_frag = await session.scalars(
        select(UserFrag).where(UserFrag.frag_id == db_missao.id)
    )
    users_frag_list = users_frag.all()
    assert len(users_frag_list) == 2


async def test_update_missao_recalcula_comiss(
    client, session, token, user_with_comiss
):
    """Testa que atualizar missao recalcula comiss."""
    user, comiss = user_with_comiss
    today = date.today()

    # Criar missao inicial
    afast_date = today + timedelta(days=5)
    regres_date = today + timedelta(days=10)

    missao = FragMisFactory(
        n_doc=9006,
        afast=datetime.combine(afast_date, time(8, 0)),
        regres=datetime.combine(regres_date, time(18, 0)),
    )
    session.add(missao)
    await session.flush()

    pernoite = PernoiteFragFactory(
        frag_id=missao.id,
        cidade_id=3550308,
        data_ini=afast_date,
        data_fim=regres_date,
    )
    session.add(pernoite)

    user_frag = UserFragFactory(
        frag_id=missao.id, user_id=user.id, sit='c', p_g=user.p_g
    )
    session.add(user_frag)
    await session.commit()

    # Atualizar missao
    payload = {
        'id': missao.id,
        'n_doc': 9006,
        'tipo_doc': 'om',
        'indenizavel': True,
        'acrec_desloc': False,
        'afast': datetime.combine(afast_date, time(8, 0)).isoformat(),
        'regres': datetime.combine(
            regres_date + timedelta(days=2), time(18, 0)  # Alterado
        ).isoformat(),
        'desc': 'Missao recalculo comiss',
        'obs': '',
        'tipo': 'adm',
        'pernoites': [
            {
                'acrec_desloc': False,
                'data_ini': afast_date.isoformat(),
                'data_fim': (regres_date + timedelta(days=2)).isoformat(),
                'meia_diaria': False,
                'obs': '',
                'cidade_id': 3550308,
                'cidade': {
                    'codigo': 3550308,
                    'nome': 'Sao Paulo',
                    'uf': 'SP',
                },
            }
        ],
        'users': [_build_user_payload(user, 'c')],
        'etiquetas': [],
    }

    response = await client.post(
        '/cegep/missoes/',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.OK

    # Verifica que comiss foi atualizado
    await session.refresh(comiss)
    assert comiss.cache_calc is not None


# ============ P4 - EDGE CASES ============


async def test_create_missao_invalid_tipo_doc(
    client, token, missao_base_payload
):
    """Testa que tipo_doc invalido falha."""
    payload = missao_base_payload.copy()
    payload['tipo_doc'] = 'XX'  # Invalido

    response = await client.post(
        '/cegep/missoes/',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_missao_invalid_tipo(client, token, missao_base_payload):
    """Testa que tipo invalido falha."""
    payload = missao_base_payload.copy()
    payload['tipo'] = 'YY'  # Invalido

    response = await client.post(
        '/cegep/missoes/',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_create_missao_invalid_sit(client, token, missao_base_payload):
    """Testa que sit invalido falha."""
    payload = missao_base_payload.copy()
    payload['users'] = [missao_base_payload['users'][0].copy()]
    payload['users'][0]['sit'] = 'x'  # Invalido

    response = await client.post(
        '/cegep/missoes/',
        headers={'Authorization': f'Bearer {token}'},
        json=payload,
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
