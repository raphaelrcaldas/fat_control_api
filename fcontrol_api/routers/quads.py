from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from fcontrol_api.database import get_session
from fcontrol_api.models import Quad, Tripulante
from fcontrol_api.schemas import QuadPublic, QuadSchema

router = APIRouter()

Session = Annotated[Session, Depends(get_session)]

router = APIRouter(prefix='/quads', tags=['quads'])


@router.post('/', response_model=QuadPublic, status_code=HTTPStatus.CREATED)
def create_quad(
    quad: QuadSchema,
    session: Session,
):
    db_quad = Quad(
        value=quad.value,
        type=quad.type,
        user_id=quad.user_id,
    )
    session.add(db_quad)
    session.commit()
    session.refresh(db_quad)

    return db_quad


@router.get('/', status_code=HTTPStatus.OK)
def list_quads(session: Session, type: str, func: str):
    query = (
        select(Quad, Tripulante)
        .join(Tripulante, Quad.user_id == Tripulante.id)
        .where(Quad.type == type)
    )

    quads = session.execute(query.filter(Tripulante.func == func)).all()

    for row in quads:
        print(row)
    # return {'quads': quads}


# @router.patch('/{quad_id}', response_model=QuadPublic)
# def patch_todo(
#     todo_id: int, session: Session, user: CurrentUser, todo: QuadUpdate
#     ):
#     db_todo = session.scalar(
#         select(Todo).where(Todo.user_id == user.id, Todo.id == todo_id)
#     )

#     if not db_todo:
#         raise HTTPException(
#             status_code=HTTPStatus.NOT_FOUND, detail='Task not found.'
#         )

#     for key, value in todo.model_dump(exclude_unset=True).items():
#         setattr(db_todo, key, value)

#     session.add(db_todo)
#     session.commit()
#     session.refresh(db_todo)

#     return db_todo
