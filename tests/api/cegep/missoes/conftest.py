"""
Fixtures para testes de Missoes CEGEP.

Os dados de seed (estados, cidades, grupos, diarias, soldos) estao
centralizados em tests/seed/ e sao carregados automaticamente.
"""

from datetime import date, datetime, time, timedelta

import pytest

from tests.factories import (
    ComissFactory,
    EtiquetaFactory,
    FragMisFactory,
    PernoiteFragFactory,
    UserFragFactory,
)


@pytest.fixture
async def etiqueta_existente(session):
    """
    Cria uma etiqueta simples para testes de CRUD.

    Returns:
        Etiqueta: Etiqueta criada no banco
    """
    etiqueta = EtiquetaFactory(
        nome='Teste', cor='#FF0000', descricao='Etiqueta de teste'
    )
    session.add(etiqueta)
    await session.commit()
    await session.refresh(etiqueta)
    return etiqueta


@pytest.fixture
async def etiquetas_lista(session):
    """
    Cria lista de etiquetas para testes de listagem.

    Returns:
        list[Etiqueta]: Lista de etiquetas
    """
    etiquetas = [
        EtiquetaFactory(nome='Alpha', cor='#FF0000'),
        EtiquetaFactory(nome='Beta', cor='#00FF00'),
        EtiquetaFactory(nome='Gamma', cor='#0000FF'),
    ]
    session.add_all(etiquetas)
    await session.commit()
    for e in etiquetas:
        await session.refresh(e)
    return etiquetas


@pytest.fixture
async def missao_existente(session, users):
    """
    Cria uma missao completa com pernoites e users para testes.

    Returns:
        FragMis: Missao criada no banco
    """
    user, _ = users
    today = date.today()

    missao = FragMisFactory(
        tipo_doc='om',
        n_doc=1001,
        desc='Missao de teste',
        tipo='adm',
        afast=datetime.combine(today + timedelta(days=10), time(8, 0)),
        regres=datetime.combine(today + timedelta(days=15), time(18, 0)),
        acrec_desloc=False,
        obs='Observacao teste',
        indenizavel=True,
    )
    session.add(missao)
    await session.flush()

    pernoite = PernoiteFragFactory(
        frag_id=missao.id,
        cidade_id=3550308,  # SP
        data_ini=today + timedelta(days=10),
        data_fim=today + timedelta(days=15),
        acrec_desloc=False,
        meia_diaria=False,
        obs='',
    )
    session.add(pernoite)

    user_frag = UserFragFactory(
        frag_id=missao.id,
        user_id=user.id,
        sit='d',  # diaria (nao requer comiss)
        p_g=user.p_g,
    )
    session.add(user_frag)

    await session.commit()
    await session.refresh(missao)

    return missao


@pytest.fixture
async def missao_com_meia_diaria(session, users):
    """
    Cria uma missao com pernoite terminando em meia-diaria.

    Util para testar conflitos de meia-diaria.

    Returns:
        FragMis: Missao com meia_diaria=True no ultimo pernoite
    """
    user, _ = users
    today = date.today()

    missao = FragMisFactory(
        tipo_doc='om',
        n_doc=2001,
        desc='Missao com meia diaria',
        tipo='adm',
        afast=datetime.combine(today + timedelta(days=20), time(8, 0)),
        regres=datetime.combine(today + timedelta(days=25), time(12, 0)),
        acrec_desloc=False,
        obs='',
        indenizavel=True,
    )
    session.add(missao)
    await session.flush()

    pernoite = PernoiteFragFactory(
        frag_id=missao.id,
        cidade_id=3550308,
        data_ini=today + timedelta(days=20),
        data_fim=today + timedelta(days=25),
        acrec_desloc=False,
        meia_diaria=True,  # Termina em meia-diaria
        obs='',
    )
    session.add(pernoite)

    user_frag = UserFragFactory(
        frag_id=missao.id,
        user_id=user.id,
        sit='d',
        p_g=user.p_g,
    )
    session.add(user_frag)

    await session.commit()
    await session.refresh(missao)

    return missao


@pytest.fixture
async def user_with_comiss(session, users):
    """
    Cria um usuario com comissionamento aberto.

    Returns:
        tuple: (user, comiss)
    """
    user, _ = users
    today = date.today()

    comiss = ComissFactory(
        user_id=user.id,
        status='aberto',
        data_ab=today - timedelta(days=30),
        data_fc=today + timedelta(days=60),
        dias_cumprir=60,
    )
    session.add(comiss)
    await session.commit()
    await session.refresh(comiss)

    return (user, comiss)


def _get_posto_for_pg(p_g: str) -> dict:
    """
    Retorna o dict do posto/graduacao para uso em payloads.

    Os dados vem do seed data (tests/seed/posto_grad.py).
    """
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


@pytest.fixture
def missao_base_payload(users):
    """
    Retorna payload base valido para criar missao via POST.

    Usa sit='d' para evitar validacao de comissionamento.

    Returns:
        dict: Payload completo para POST /cegep/missoes/
    """
    user, _ = users
    today = date.today()
    posto = _get_posto_for_pg(user.p_g)

    return {
        'n_doc': 3001,
        'tipo_doc': 'om',
        'indenizavel': True,
        'acrec_desloc': False,
        'afast': datetime.combine(
            today + timedelta(days=30), time(8, 0)
        ).isoformat(),
        'regres': datetime.combine(
            today + timedelta(days=35), time(18, 0)
        ).isoformat(),
        'desc': 'Missao via payload',
        'obs': 'Observacao',
        'tipo': 'adm',
        'pernoites': [
            {
                'acrec_desloc': False,
                'data_ini': (today + timedelta(days=30)).isoformat(),
                'data_fim': (today + timedelta(days=35)).isoformat(),
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
            {
                'user_id': user.id,
                'p_g': user.p_g,
                'sit': 'd',  # diaria - nao requer comiss
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
        ],
        'etiquetas': [],
    }


@pytest.fixture
def missao_payload_comiss(user_with_comiss):
    """
    Retorna payload para criar missao com sit='c' (comissionado).

    Requer usuario com comissionamento valido.

    Returns:
        dict: Payload completo para POST /cegep/missoes/
    """
    user, comiss = user_with_comiss
    today = date.today()
    posto = _get_posto_for_pg(user.p_g)

    # Missao deve estar dentro do periodo do comissionamento
    afast_date = today + timedelta(days=5)
    regres_date = today + timedelta(days=10)

    return {
        'n_doc': 4001,
        'tipo_doc': 'om',
        'indenizavel': True,
        'acrec_desloc': False,
        'afast': datetime.combine(afast_date, time(8, 0)).isoformat(),
        'regres': datetime.combine(regres_date, time(18, 0)).isoformat(),
        'desc': 'Missao comissionada',
        'obs': 'Observacao',
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
        'users': [
            {
                'user_id': user.id,
                'p_g': user.p_g,
                'sit': 'c',  # comissionado
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
        ],
        'etiquetas': [],
    }
