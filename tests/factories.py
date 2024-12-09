import datetime
import typing

import factory
import factory.fuzzy

from fcontrol_api.models import User
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


# class TripFactory(factory.Factory):
#     class Meta:
#         model = Tripulante

#     id: int
#     trig = factory.fuzzy.FuzzyText(length=3)
#     func = factory.fuzzy.FuzzyChoice([e.value for e in FuncList])
#     oper = factory.fuzzy.FuzzyChoice([e.value for e in OperList])
#     active = True


# class QuadFactory(factory.Factory):
#     class Meta:
#         model = Quad

#     type = factory.fuzzy.FuzzyChoice(QuadType)
