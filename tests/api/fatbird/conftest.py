"""Fixtures do POV do FatBird (portal do tripulante).

O ponto central: um tripulante do FatBird **não tem `user_roles`**. O
`get_user_roles` devolve `role=None`/`perms=[]` — não há fallback por
`app_client`. Logo, qualquer `permission_checker` num GET compartilhado
que o portal consome devolve 403 e, como os fetchers do FatBird engolem
erro como "sem dado", vira regressão **silenciosa**.

Por isso estas fixtures NÃO podem usar `make_org_token`/`token_sem_perm` do
conftest de cima: eles **injetam uma role admin** quando o usuário não
tem nenhuma (bypass), o que mascararia exatamente o bug que queremos
pegar. Aqui o token é forjado na mão, sem role, com
`app_client='fatbird'` (o que `validate_user_client_access` exige é ser
tripulante ativo, não ter role).
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from fcontrol_api.models.shared.users import User
from fcontrol_api.security import create_access_token
from tests.factories import TripFactory, UserFactory

ORG = '11gt'


async def _mk_tripulante(session, *, unidade=ORG):
    """Cria um militar ativo + vínculo de tripulante ativo, SEM role."""
    user = UserFactory(unidade=unidade)
    user.active = True
    session.add(user)
    await session.flush()

    trip = TripFactory(user_id=user.id, uae=unidade, active=True)
    session.add(trip)
    await session.commit()

    db_user = await session.scalar(
        select(User)
        .where(User.id == user.id)
        .options(selectinload(User.posto))
    )
    return db_user, trip


def _fatbird_token(user, active_org=ORG):
    """Token como o portal emite: app_client 'fatbird' e org da lotação."""
    return create_access_token(
        data={
            'sub': f'{user.posto.short} {user.nome_guerra}',
            'user_id': user.id,
            'app_client': 'fatbird',
            'active_org': active_org,
        }
    )


@pytest.fixture
async def trip_user(session):
    """Tripulante ativo da '11gt' sem nenhuma role (POV do FatBird)."""
    user, trip = await _mk_tripulante(session)
    return user, trip


@pytest.fixture
async def trip_token(trip_user):
    """Token FatBird do próprio tripulante (sem role, sem permissões)."""
    user, _ = trip_user
    return _fatbird_token(user)


@pytest.fixture
async def outro_trip(session):
    """Um segundo tripulante da mesma org — o 'terceiro' das checagens."""
    user, trip = await _mk_tripulante(session)
    return user, trip


def auth(token):
    return {'Authorization': f'Bearer {token}'}
