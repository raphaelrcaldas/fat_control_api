from datetime import date
from http import HTTPStatus

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.enums.posto_grad import PostoGradEnum
from fcontrol_api.models.shared.posto_grad import PostoGrad
from fcontrol_api.models.shared.users import User, UserPromo


async def check_user_conflicts(
    session: AsyncSession,
    saram: str | None = None,
    id_fab: str | None = None,
    cpf: str | None = None,
    email_fab: str | None = None,
    email_pess: str | None = None,
    exclude_user_id: int | None = None,
) -> None:
    """
    Verifica conflitos de unicidade no banco.
    Lança HTTPException em caso de conflito.

    Parâmetros opcionais: verifica apenas campos não-None.
    exclude_user_id: quando informado, ignora esse id (útil em updates).
    """
    # SARAM
    if saram:
        q = select(User).where(User.saram == saram)
        if exclude_user_id is not None:
            q = q.where(User.id != exclude_user_id)
        exists = await session.scalar(q)
        if exists:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='SARAM já registrado',
            )

    # ID FAB
    if id_fab:
        q = select(User).where(User.id_fab == id_fab)
        if exclude_user_id is not None:
            q = q.where(User.id != exclude_user_id)
        exists = await session.scalar(q)
        if exists:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='ID FAB já registrado',
            )

    # CPF
    if cpf:
        q = select(User).where(User.cpf == cpf)
        if exclude_user_id is not None:
            q = q.where(User.id != exclude_user_id)
        exists = await session.scalar(q)
        if exists:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='CPF já registrado',
            )

    # EMAIL FAB (Zimbra)
    if email_fab:
        q = select(User).where(User.email_fab == email_fab)
        if exclude_user_id is not None:
            q = q.where(User.id != exclude_user_id)
        exists = await session.scalar(q)
        if exists:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='Zimbra já registrado',
            )

    # EMAIL PESSOAL
    if email_pess:
        q = select(User).where(User.email_pess == email_pess)
        if exclude_user_id is not None:
            q = q.where(User.id != exclude_user_id)
        exists = await session.scalar(q)
        if exists:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='Email pessoal já registrado',
            )


async def validate_promo_hierarchy(
    session: AsyncSession,
    user_id: int,
    p_g: PostoGradEnum,
    data_promo: date,
) -> None:
    """
    Valida a coerência de uma nova promoção no histórico de carreira.

    Regra de negócio (posto_grad.ant define a hierarquia: menor `ant` =
    graduação superior). A linha do tempo de promoções deve ser
    estritamente ascendente: à medida que a data aumenta, a graduação
    deve subir (o `ant` deve diminuir).

    Levanta HTTPException em caso de:
    - p_g inexistente em posto_grad;
    - data já utilizada em outra promoção do usuário;
    - graduação já registrada no histórico do usuário;
    - quebra da progressão ascendente em relação à promoção
      cronologicamente anterior ou posterior.
    """
    # Antiguidade da graduação alvo
    ant_novo = await session.scalar(
        select(PostoGrad.ant).where(PostoGrad.short == p_g.value)
    )
    if ant_novo is None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Graduação inválida',
        )

    # Histórico atual do usuário com a antiguidade de cada graduação
    rows = (
        await session.execute(
            select(
                UserPromo.id,
                UserPromo.p_g,
                UserPromo.data_promo,
                PostoGrad.ant,
            )
            .join(PostoGrad, PostoGrad.short == UserPromo.p_g)
            .where(UserPromo.user_id == user_id)
            .order_by(UserPromo.data_promo)
        )
    ).all()

    prev_row = None  # promoção cronologicamente anterior
    next_row = None  # promoção cronologicamente posterior
    for row in rows:
        if row.p_g == p_g.value:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='Graduação já registrada no histórico do militar',
            )
        if row.data_promo == data_promo:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='Já existe uma promoção registrada nesta data',
            )
        if row.data_promo < data_promo:
            prev_row = row
        elif next_row is None:
            next_row = row

    if prev_row is not None and prev_row.ant <= ant_novo:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=(
                'A graduação deve ser superior à promoção anterior '
                'na linha do tempo'
            ),
        )

    if next_row is not None and next_row.ant >= ant_novo:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=(
                'A graduação deve ser inferior à promoção posterior '
                'na linha do tempo'
            ),
        )
