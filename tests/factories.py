"""
Factories para criação de objetos de teste usando factory_boy.
"""

import datetime
import typing

import factory
import factory.fuzzy

from fcontrol_api.enums.indisp import IndispEnum
from fcontrol_api.models.public.funcoes import Funcao
from fcontrol_api.models.public.indisp import Indisp
from fcontrol_api.models.public.om import OrdemEtapa, OrdemMissao
from fcontrol_api.models.public.quads import Quad
from fcontrol_api.models.public.tripulantes import Tripulante
from fcontrol_api.models.public.users import User
from fcontrol_api.models.security.auth import OAuth2Client
from fcontrol_api.schemas.funcoes import funcs, opers, proj
from fcontrol_api.schemas.tripulantes import uaes
from fcontrol_api.utils.validators import calcular_dv_saram


def gerar_cpf_valido(n: int) -> str:
    """
    Gera um CPF válido com dígitos verificadores corretos.

    Args:
        n: Número sequencial para gerar o CPF base

    Returns:
        CPF válido (11 dígitos) com DVs corretos
    """
    # Gera os 9 primeiros dígitos
    base = str(n).zfill(9)

    # Calcula primeiro DV
    soma = sum(int(base[i]) * (10 - i) for i in range(9))
    resto = soma % 11
    dv1 = 0 if resto < 2 else 11 - resto

    # Calcula segundo DV
    base_com_dv1 = base + str(dv1)
    soma = sum(int(base_com_dv1[i]) * (11 - i) for i in range(10))
    resto = soma % 11
    dv2 = 0 if resto < 2 else 11 - resto

    return base + str(dv1) + str(dv2)


def gerar_saram_valido(n: int) -> str:
    """
    Gera um SARAM válido com dígito verificador correto.

    Args:
        n: Número sequencial para gerar o SARAM base

    Returns:
        SARAM válido (7 dígitos) com DV correto como string
    """
    # Gera um número base de 6 dígitos
    numero_base = str(100000 + n)
    # Calcula o DV
    dv = calcular_dv_saram(numero_base)
    # Retorna o SARAM completo como string
    return numero_base + str(dv)


class UserFactory(factory.Factory):
    """
    Factory para criar usuários de teste.
    """

    class Meta:
        model = User

    p_g = factory.fuzzy.FuzzyChoice(['2s', '3s', 'cb'])
    esp = factory.fuzzy.FuzzyText(length=3)
    nome_guerra = factory.Sequence(lambda n: f'fulano{n}')
    nome_completo = factory.Sequence(lambda n: f'fulano{n} da silva')
    id_fab = factory.Sequence(lambda n: str(100000 + n))
    saram = factory.Sequence(gerar_saram_valido)
    unidade = factory.fuzzy.FuzzyText(length=5)
    cpf = factory.Sequence(gerar_cpf_valido)
    email_fab = factory.LazyAttribute(
        lambda obj: f'{obj.nome_guerra}@fab.mil.br'
    )
    email_pess = factory.LazyAttribute(
        lambda obj: f'{obj.nome_guerra}@email.mil.br'
    )
    ant_rel = factory.fuzzy.FuzzyInteger(1, 999)
    nasc = factory.fuzzy.FuzzyDate(datetime.date(1970, 1, 1))
    ult_promo = factory.fuzzy.FuzzyDate(datetime.date(2010, 1, 1))
    password = factory.LazyAttribute(lambda obj: f'{obj.nome_guerra}-secret')


class TripFactory(factory.Factory):
    """
    Factory para criar tripulantes.
    """

    class Meta:
        model = Tripulante

    user_id: int
    trig = factory.Sequence(
        lambda n: f'{chr(97 + n % 26)}{chr(97 + (n // 26) % 26)}'
        f'{chr(97 + (n // 676) % 26)}'
    )
    active = True  # Padrão ativo (mais comum em testes)
    uae = factory.fuzzy.FuzzyChoice(typing.get_args(uaes))


class FuncFactory(factory.Factory):
    """
    Factory para criar funções vinculadas a tripulantes.
    """

    class Meta:
        model = Funcao

    trip_id: int
    func = factory.fuzzy.FuzzyChoice(typing.get_args(funcs))
    oper = factory.fuzzy.FuzzyChoice(typing.get_args(opers))
    proj = factory.fuzzy.FuzzyChoice(typing.get_args(proj))
    data_op = None


class QuadFactory(factory.Factory):
    """
    Factory para criar quadrantes vinculados a tripulantes.

    ATENÇÃO: Esta factory requer seed data para quads_type.
    O type_id hardcoded (1) assume que existe um quads_type.id = 1
    no banco de dados.

    IMPORTANTE: Requer trip_id ao criar.

    Status: ⚠️ DESABILITADA até seed data de quads_type ser criada.

    Uso (quando habilitada):
        quad = QuadFactory(trip_id=trip.id)
        quad_especifico = QuadFactory(
            trip_id=trip.id,
            type_id=2,
            description='Descrição customizada'
        )

    TODO: Criar seed data para quads_type ou usar SubFactory
    """

    class Meta:
        model = Quad

    description = factory.fuzzy.FuzzyText(length=6)
    type_id = 1  # ⚠️ HARDCODED - requer quads_type.id = 1 no seed
    value = factory.fuzzy.FuzzyDate(datetime.date(2024, 1, 1))
    trip_id: int


class OAuth2ClientFactory(factory.Factory):
    """
    Factory para criar clientes OAuth2.
    """

    class Meta:
        model = OAuth2Client

    client_id = factory.Sequence(lambda n: f'test-client-{n}')
    client_secret = factory.fuzzy.FuzzyText(length=32)
    redirect_uri = 'http://localhost:3000/callback'
    is_confidential = False


class IndispFactory(factory.Factory):
    """
    Factory para criar indisponibilidades de teste.

    IMPORTANTE: Requer user_id e created_by ao criar.

    Uso:
        indisp = IndispFactory(user_id=user.id, created_by=creator.id)
        indisp_ferias = IndispFactory(
            user_id=user.id,
            created_by=creator.id,
            mtv='fer',
            obs='Ferias programadas'
        )
    """

    class Meta:
        model = Indisp

    user_id: int
    created_by: int
    date_start = factory.LazyFunction(datetime.date.today)
    date_end = factory.LazyAttribute(
        lambda _: datetime.date.today() + datetime.timedelta(days=7)
    )
    mtv = factory.fuzzy.FuzzyChoice([e.value for e in IndispEnum])
    obs = factory.Sequence(lambda n: f'Observacao teste {n}')


class OrdemMissaoFactory(factory.Factory):
    """
    Factory para criar Ordens de Missão de teste.

    IMPORTANTE: Requer created_by ao criar.

    Uso:
        ordem = OrdemMissaoFactory(created_by=user.id)
        ordem_rascunho = OrdemMissaoFactory(
            created_by=user.id,
            status='rascunho'
        )
    """

    class Meta:
        model = OrdemMissao

    numero = factory.Sequence(lambda n: f'OM-{n:04d}/2025')
    matricula_anv = factory.fuzzy.FuzzyInteger(2800, 2899)
    tipo = factory.fuzzy.FuzzyChoice(
        ['instrucao', 'operacional', 'transporte']
    )
    created_by: int
    projeto = factory.fuzzy.FuzzyChoice(['ABAFA', 'ACAO', 'INST'])
    status = 'aprovada'
    campos_especiais = []
    uae = factory.fuzzy.FuzzyChoice(['1/1 GT', '2/1 GT', '3/1 GT'])
    esf_aer = factory.fuzzy.FuzzyInteger(0, 5)


class OrdemEtapaFactory(factory.Factory):
    """
    Factory para criar Etapas de Ordem de Missão de teste.

    IMPORTANTE: Requer ordem_id ao criar.

    Uso:
        etapa = OrdemEtapaFactory(ordem_id=ordem.id)
        etapa_especifica = OrdemEtapaFactory(
            ordem_id=ordem.id,
            origem='SBGL',
            dest='SBBR',
            alternativa='SBCF'
        )
    """

    class Meta:
        model = OrdemEtapa

    ordem_id: int
    dt_dep = factory.LazyFunction(
        lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    origem = factory.fuzzy.FuzzyChoice(['SBGL', 'SBGR', 'SBRF', 'SBCF'])
    dest = factory.fuzzy.FuzzyChoice(['SBBR', 'SBSP', 'SBJD', 'SBSV'])
    dt_arr = factory.LazyAttribute(
        lambda obj: obj.dt_dep + datetime.timedelta(hours=1)
    )
    alternativa = factory.fuzzy.FuzzyChoice(['SBCF', 'SBSP', 'SBGL', 'SBBR'])
    tvoo_etp = 60  # 1 hora em minutos
    tvoo_alt = 30  # 30 minutos
    qtd_comb = factory.fuzzy.FuzzyInteger(10, 20)
    esf_aer = factory.fuzzy.FuzzyText(length=10)
