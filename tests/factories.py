import factory
import factory.fuzzy

from fcontrol_api.models import FuncList, OperList, Quad, QuadType, Tripulante

# class UserFactory(factory.Factory):
#     class Meta:
#         model = User

#     username = factory.Sequence(lambda n: f'test{n}')
#     email = factory.LazyAttribute(lambda obj: f'{obj.username}@test.com')
#     password = factory.LazyAttribute(
#         lambda obj: f'{obj.username}@example.com'
#         )


class TripFactory(factory.Factory):
    class Meta:
        model = Tripulante

    id: int
    trig = factory.fuzzy.FuzzyText(length=3)
    func = factory.fuzzy.FuzzyChoice([e.value for e in FuncList])
    oper = factory.fuzzy.FuzzyChoice([e.value for e in OperList])
    active = True


class QuadFactory(factory.Factory):
    class Meta:
        model = Quad

    type = factory.fuzzy.FuzzyChoice(QuadType)
