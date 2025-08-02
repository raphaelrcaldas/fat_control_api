from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.comiss import Comissionamento
from fcontrol_api.models.cegep.diarias import GrupoCidade, GrupoPg
from fcontrol_api.models.cegep.missoes import FragMis, UserFrag
from fcontrol_api.schemas.comiss import ComissSchema
from fcontrol_api.schemas.missoes import FragMisSchema
from fcontrol_api.schemas.users import UserPublic
from fcontrol_api.services.financeiro import cache_diarias
from fcontrol_api.utils.financeiro import custo_missao, verificar_modulo

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/comiss', tags=['CEGEP'])


@router.get('/')
async def get_cmtos(session: Session):
    query = (
        select(Comissionamento, FragMis, UserFrag)
        .join(
            UserFrag,
            and_(
                UserFrag.user_id == Comissionamento.user_id,
                UserFrag.sit == 'c',
            ),
            isouter=True,
        )
        .join(
            FragMis,
            and_(
                FragMis.id == UserFrag.frag_id,
                FragMis.afast >= Comissionamento.data_ab,
                FragMis.regres <= Comissionamento.data_fc,
            ),
            isouter=True,
        )
        .where(Comissionamento.status == 'aberto')
    )

    result = await session.execute(query)
    registros: list[tuple[Comissionamento, FragMis, UserFrag]] = result.all()

    # Cache de valores de diária por grupo
    valores_cache = await cache_diarias(session)

    # Cache de grupos
    grupos_pg = dict(
        (await session.execute(select(GrupoPg.pg_short, GrupoPg.grupo))).all()
    )
    grupos_cidade = dict(
        (
            await session.execute(
                select(GrupoCidade.cidade_id, GrupoCidade.grupo)
            )
        ).all()
    )

    agrupado: dict[int, dict] = {}

    for comiss, missao, user_frag in registros:
        user = UserPublic.model_validate(comiss.user).model_dump()
        comiss = ComissSchema.model_validate(comiss).model_dump(
            exclude={'user_id'},
        )

        if comiss['id'] not in agrupado:
            comiss['user'] = user
            agrupado[comiss['id']] = {
                **comiss,
                'missoes': [],
                'dias_comp': 0,
                'diarias_comp': 0,
                'vals_comp': 0,
                'modulo': False,
            }

        comiss_ag = agrupado[comiss['id']]

        if missao:
            missao = FragMisSchema.model_validate(missao).model_dump(
                exclude={'users'}
            )
            missao = custo_missao(
                user_frag.p_g,
                user_frag.sit,
                missao,
                grupos_pg,
                grupos_cidade,
                valores_cache,
            )
            comiss_ag['diarias_comp'] += missao['diarias']
            comiss_ag['missoes'].append(missao)
            comiss_ag['dias_comp'] += missao['dias']
            comiss_ag['vals_comp'] += missao['valor_total']

    response = list(agrupado.values())
    for c in response:
        c['modulo'] = verificar_modulo(c['missoes'])

    return response


@router.put('/')
async def create_cmto(
    session: Session,
    comiss: ComissSchema,
):
    db_comiss = await session.scalar(
        select(Comissionamento).where(
            (Comissionamento.user_id == comiss.user_id)
            & (Comissionamento.status == 'aberto')
        )
    )
    if db_comiss:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Já existe um comissionamento aberto para este usuário.',
        )

    comiss_data = ComissSchema.model_validate(comiss).model_dump(
        exclude={'id'}
    )
    new_comiss = Comissionamento(**comiss_data)

    session.add(new_comiss)

    await session.commit()

    return {'detail': 'Comissionamento criado com sucesso'}
