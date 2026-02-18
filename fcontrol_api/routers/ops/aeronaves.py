from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.public.aeronaves import Aeronave
from fcontrol_api.schemas.ops.aeronave import (
    AeronaveCreate,
    AeronavePublic,
    AeronaveUpdate,
)
from fcontrol_api.schemas.response import (
    ApiPaginatedResponse,
    ApiResponse,
)
from fcontrol_api.utils.responses import (
    paginated_response,
    success_response,
)

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/aeronaves', tags=['aeronaves'])


@router.post(
    '/',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[AeronavePublic],
)
async def create_aeronave(
    aeronave: AeronaveCreate,
    session: Session,
):
    db_aeronave = await session.scalar(
        select(Aeronave).where(
            Aeronave.matricula == aeronave.matricula
        )
    )

    if db_aeronave:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Aeronave com esta matrícula já existe',
        )

    new_aeronave = Aeronave(
        matricula=aeronave.matricula,
        active=aeronave.active,
        sit=aeronave.sit,
        obs=aeronave.obs,
    )

    session.add(new_aeronave)
    await session.commit()
    await session.refresh(new_aeronave)

    return success_response(
        data=AeronavePublic.model_validate(new_aeronave),
        message='Aeronave cadastrada com sucesso',
    )


@router.get(
    '/',
    status_code=HTTPStatus.OK,
    response_model=ApiPaginatedResponse[AeronavePublic],
)
async def list_aeronaves(
    session: Session,
    sit: str | None = None,
    active: bool | None = None,
    page: int = 1,
    per_page: int = 100,
):
    per_page = min(per_page, 100)
    page = max(page, 1)
    offset = (page - 1) * per_page

    base_query = select(Aeronave).order_by(
        Aeronave.matricula
    )
    count_query = select(func.count()).select_from(
        Aeronave
    )

    filters = []

    if sit:
        sit_list = [
            s.strip()
            for s in sit.split(',')
            if s.strip()
        ]
        if len(sit_list) == 1:
            filters.append(Aeronave.sit == sit_list[0])
        elif len(sit_list) > 1:
            filters.append(Aeronave.sit.in_(sit_list))

    if active is not None:
        filters.append(Aeronave.active == active)

    for f in filters:
        base_query = base_query.where(f)
        count_query = count_query.where(f)

    total = await session.scalar(count_query) or 0
    result = await session.scalars(
        base_query.offset(offset).limit(per_page)
    )
    aeronaves = result.all()

    return paginated_response(
        items=[
            AeronavePublic.model_validate(a)
            for a in aeronaves
        ],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get(
    '/{matricula}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[AeronavePublic],
)
async def get_aeronave(
    matricula: str, session: Session
):
    db_aeronave = await session.scalar(
        select(Aeronave).where(
            Aeronave.matricula == matricula
        )
    )

    if not db_aeronave:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Aeronave não encontrada',
        )

    return success_response(
        data=AeronavePublic.model_validate(db_aeronave),
    )


@router.put(
    '/{matricula}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[AeronavePublic],
)
async def update_aeronave(
    matricula: str,
    aeronave: AeronaveUpdate,
    session: Session,
):
    db_aeronave = await session.scalar(
        select(Aeronave).where(
            Aeronave.matricula == matricula
        )
    )

    if not db_aeronave:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Aeronave não encontrada',
        )

    for key, value in aeronave.model_dump(
        exclude_unset=True
    ).items():
        setattr(db_aeronave, key, value)

    await session.commit()
    await session.refresh(db_aeronave)

    return success_response(
        data=AeronavePublic.model_validate(db_aeronave),
        message='Aeronave atualizada com sucesso',
    )
