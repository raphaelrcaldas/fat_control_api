import datetime
import typing

import factory
import factory.fuzzy

from fcontrol_api.models import Funcao, Tripulante, User
from fcontrol_api.schemas.funcoes import funcs, opers, proj
from fcontrol_api.schemas.tripulantes import uaes
from fcontrol_api.schemas.users import p_gs


class UserFactory(factory.Factory):
    class Meta:
        model = User

    p_g = factory.fuzzy.FuzzyChoice(typing.get_args(p_gs))
    esp = factory.fuzzy.FuzzyText(length=3)
    nome_guerra = factory.Sequence(lambda n: f'fulano{n}')
    nome_completo = factory.Sequence(lambda n: f'fulano{n} da silva')
    id_fab = factory.fuzzy.FuzzyInteger(100000, 999999)
    saram = factory.fuzzy.FuzzyInteger(1000000, 9999999)
    unidade = factory.fuzzy.FuzzyText(length=5)
    cpf = factory.Sequence(lambda n: f'0000000000{n}')
    email_fab = factory.LazyAttribute(
        lambda obj: f'{obj.nome_guerra}@fab.mil.br'
    )
    email_pess = factory.LazyAttribute(
        lambda obj: f'{obj.nome_guerra}@email.mil.br'
    )
    nasc = factory.fuzzy.FuzzyDate(datetime.date(1970, 1, 1))
    ult_promo = factory.fuzzy.FuzzyDate(datetime.date(2010, 1, 1))
    password = factory.LazyAttribute(lambda obj: f'{obj.nome_guerra}-secret')


class TripFactory(factory.Factory):
    class Meta:
        model = Tripulante

    user_id: int
    trig = factory.Sequence(lambda n: f'ab{chr(96 + n)}')
    active = factory.fuzzy.FuzzyChoice([True, False])
    uae = factory.fuzzy.FuzzyChoice(typing.get_args(uaes))


class FuncFactory(factory.Factory):
    class Meta:
        model = Funcao

    trip_id: int
    func = factory.fuzzy.FuzzyChoice(typing.get_args(funcs))
    oper = factory.fuzzy.FuzzyChoice(typing.get_args(opers))
    proj = factory.fuzzy.FuzzyChoice(typing.get_args(proj))
    data_op = None


# class QuadFactory(factory.Factory):
#     class Meta:
#         model = Quad

#     type = factory.fuzzy.FuzzyChoice(QuadType)
