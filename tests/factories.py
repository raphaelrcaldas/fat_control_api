"""
Factories para criação de objetos de teste usando factory_boy.
"""

import datetime
import typing

import factory
import factory.fuzzy

from fcontrol_api.models.public.funcoes import Funcao
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
    trig = factory.Sequence(lambda n: f'ab{chr(96 + n)}')
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
