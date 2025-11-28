import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.models.public.users import User

pytestmark = pytest.mark.anyio


async def test_create_user(session: AsyncSession):
    new_user = User(
        p_g='2s',
        esp=None,
        nome_guerra='fulano',
        nome_completo=None,
        id_fab=None,
        saram=5555555,
        unidade='11gt',
        cpf=None,
        email_fab=None,
        email_pess=None,
        nasc=None,
        ult_promo=None,
        ant_rel=None,
        password='secret',
    )
    session.add(new_user)
    await session.commit()

    user: User = await session.scalar(
        select(User).where(User.saram == new_user.saram)
    )

    assert user.nome_guerra == 'fulano'
