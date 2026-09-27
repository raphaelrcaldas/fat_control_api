"""Fixtures da conversa de feedback.

O AUTOR dos feedbacks de teste é `users[1]`, nunca `users[0]`:
`token_sistema` (o admin que responde) pertence a `users[0]`, e o
serviço de notificação não avisa quem causou o evento — com o mesmo
usuário nos dois papéis os testes de aviso passariam vazios.
"""

import pytest

from fcontrol_api.models.shared.feedback import Feedback
from tests.factories import TripFactory

ORG = '11gt'


@pytest.fixture
async def autor(session, users):
    """`users[1]` como tripulante ativo (o token do FatBird exige)."""
    _, other_user = users
    session.add(TripFactory(user_id=other_user.id, uae=ORG))
    await session.commit()
    return other_user


@pytest.fixture
def make_feedback(session):
    async def _make(
        user, *, status='aberto', titulo='Botão não salva', origem='fatbird'
    ):
        feedback = Feedback(
            user_id=user.id,
            uae=ORG,
            tipo='bug',
            titulo=titulo,
            descricao='Ao salvar a missão, nada acontece.',
            status=status,
            origem=origem,
        )
        session.add(feedback)
        await session.commit()
        await session.refresh(feedback)
        return feedback

    return _make


@pytest.fixture
async def feedback(make_feedback, autor):
    return await make_feedback(autor)
