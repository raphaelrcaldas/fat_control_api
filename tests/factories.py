import factory
import factory.fuzzy

from fcontrol_api.models import FuncList, OperList, Tripulante, User


class UserFactory(factory.Factory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f'test{n}')
    email = factory.LazyAttribute(lambda obj: f'{obj.username}@test.com')
    password = factory.LazyAttribute(lambda obj: f'{obj.username}@example.com')


class TripFactory(factory.Factory):
    class Meta:
        model = Tripulante

    user_id: int
    trig = factory.fuzzy.FuzzyText(length=3)
    func = factory.fuzzy.FuzzyChoice([e.value for e in FuncList])
    oper = factory.fuzzy.FuzzyChoice([e.value for e in OperList])
    active = True
