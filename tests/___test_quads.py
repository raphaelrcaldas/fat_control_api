import factory.fuzzy

from fcontrol_api.models import Quad, QuadType


def test_create_quad(client, token):
    response = client.post(
        '/quads/',
        headers={'Authorization': f'Bearer {token}'},
        json={'type': 'local', 'user_id': 5, 'value': 1},
    )

    assert response.json() == {
        'id': 1,
        'type': 'local',
        'user_id': 5,
        'value': 1,
    }


class QuadFactory(factory.Factory):
    class Meta:
        model = Quad

    type = factory.fuzzy.FuzzyChoice(QuadType)


# def test_list_quads_should_return_5_quads(session, client, user, token):
#     expected_todos = 5
#     session.bulk_save_objects(
#         QuadFactory.create_batch(5, user_id=user.id))
#     session.commit()

#     response = client.get(
#         '/quads/',
#         # headers={'Authorization': f'Bearer {token}'},
#     )

#     assert len(response.json()['quads']) == expected_todos
