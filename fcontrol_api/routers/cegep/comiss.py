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
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.comiss import ComissSchema
from fcontrol_api.schemas.missoes import FragMisSchema
from fcontrol_api.schemas.users import UserPublic
from fcontrol_api.services.comis import verificar_conflito_comiss
from fcontrol_api.services.financeiro import cache_diarias
from fcontrol_api.utils.financeiro import custo_missao, verificar_modulo

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/comiss', tags=['CEGEP'])


@router.get('/')
async def get_cmtos(
    session: Session,
    user_id: int = None,
    status: str = None,
    search: str = None,
):
    query_comiss = (
        select(Comissionamento.id)
        .join(User)
        .order_by(Comissionamento.data_ab.desc())
    )

    if user_id:
        query_comiss = query_comiss.where(Comissionamento.user_id == user_id)

    if status:
        query_comiss = query_comiss.where(Comissionamento.status == status)

        if status == 'fechado':
            query_comiss = query_comiss.limit(20)

    if search:
        query_comiss = query_comiss.where(
            User.nome_guerra.ilike(f'%{search}%')
            | User.nome_completo.ilike(f'%{search}%')
        )

    comiss_valids = await session.execute(query_comiss)
    comiss_ids = [id for (id,) in comiss_valids.all()]

    if not comiss_ids:
        return []

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
        .where(Comissionamento.id.in_(comiss_ids))
        .order_by(FragMis.afast)
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
        comiss_data = ComissSchema.model_validate(comiss).model_dump(
            exclude={'user_id'},
        )

        if comiss_data['id'] not in agrupado:
            comiss_data['user'] = user
            agrupado[comiss_data['id']] = {
                **comiss_data,
                'missoes': [],
                'dias_comp': 0,
                'diarias_comp': 0,
                'vals_comp': 0,
                'modulo': False,
                'completude': 0,
            }

        comiss_ag = agrupado[comiss_data['id']]

        if missao:
            missao_data = FragMisSchema.model_validate(missao).model_dump(
                exclude={'users'}
            )
            missao_data = custo_missao(
                user_frag.p_g,
                user_frag.sit,
                missao_data,
                grupos_pg,
                grupos_cidade,
                valores_cache,
            )
            comiss_ag['diarias_comp'] += missao_data['diarias']
            comiss_ag['missoes'].append(missao_data)
            comiss_ag['dias_comp'] += missao_data['dias']
            comiss_ag['vals_comp'] += missao_data['valor_total']

    response = list(agrupado.values())
    for c in response:
        c['modulo'] = verificar_modulo(c['missoes'])

        if c.get('dias_cumprir'):
            completude = (
                c['dias_comp'] / c['dias_cumprir'] if c['dias_cumprir'] else 0
            )
        else:
            soma_cumprir = c['valor_aj_ab'] + c['valor_aj_fc']
            completude = c['vals_comp'] / soma_cumprir

        if completude > 1:
            completude = 1

        c['completude'] = round(completude, 3)

    return response


@router.post('/')
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

    await verificar_conflito_comiss(
        comiss.user_id, comiss.data_ab, comiss.data_fc, session
    )

    comiss_data = ComissSchema.model_validate(comiss).model_dump(
        exclude={'id'}
    )
    new_comiss = Comissionamento(**comiss_data)

    session.add(new_comiss)

    await session.commit()

    return {'detail': 'Comissionamento criado com sucesso'}


@router.put('/{comiss_id}')
async def update_cmto(
    comiss_id: int,
    session: Session,
    comiss: ComissSchema,
):
    db_comiss = await session.scalar(
        select(Comissionamento).where((Comissionamento.id == comiss_id))
    )

    if not db_comiss:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Comissionamento não encontrado',
        )

    await verificar_conflito_comiss(
        comiss.user_id, comiss.data_ab, comiss.data_fc, session, comiss_id
    )

    mis_comiss = await session.scalars(
        select(FragMis, Comissionamento)
        .join(
            UserFrag,
            and_(
                UserFrag.user_id == Comissionamento.user_id,
                UserFrag.sit == 'c',
            ),
        )
        .join(
            FragMis,
            and_(
                FragMis.id == UserFrag.frag_id,
                FragMis.afast >= Comissionamento.data_ab,
                FragMis.regres <= Comissionamento.data_fc,
            ),
        )
        .where(Comissionamento.id == comiss_id)
    )
    mis_comiss = mis_comiss.all()

    mis_update_comiss = await session.scalars(
        select(FragMis, Comissionamento)
        .join(
            UserFrag,
            and_(
                UserFrag.user_id == Comissionamento.user_id,
                UserFrag.sit == 'c',
            ),
        )
        .join(
            FragMis,
            and_(
                FragMis.id == UserFrag.frag_id,
                FragMis.afast >= comiss.data_ab,
                FragMis.regres <= comiss.data_fc,
            ),
        )
        .where(Comissionamento.id == comiss_id)
    )
    mis_update_comiss = mis_update_comiss.all()

    mis_not_found: list[FragMis] = []
    for mis in mis_comiss:
        try:
            mis_update_comiss.index(mis)
        except ValueError:
            mis_not_found.append(mis)

    if mis_not_found:
        msg = '\nAs seguintes missões ficarão fora do escopo:\n'

        for mis in mis_not_found:
            msg += f'- {mis.tipo_doc} {mis.n_doc} {mis.afast}\n'.upper()

        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=msg,
        )

    for key, value in comiss.model_dump(exclude_unset=True).items():
        setattr(db_comiss, key, value)

    await session.commit()
    await session.refresh(db_comiss)

    return {'detail': 'Comissionamento atualizado com sucesso'}


@router.delete('/{comiss_id}')
async def delete_cmto(
    comiss_id: int,
    session: Session,
):
    db_comiss = await session.scalar(
        select(Comissionamento).where((Comissionamento.id == comiss_id))
    )

    if not db_comiss:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Comissionamento não encontrado',
        )

    comiss_missoes = await session.scalar(
        select(Comissionamento, FragMis, UserFrag)
        .join(
            UserFrag,
            and_(
                UserFrag.user_id == Comissionamento.user_id,
                UserFrag.sit == 'c',
            ),
        )
        .join(
            FragMis,
            and_(
                FragMis.id == UserFrag.frag_id,
                FragMis.afast >= Comissionamento.data_ab,
                FragMis.regres <= Comissionamento.data_fc,
            ),
        )
        .where(Comissionamento.id == comiss_id)
    )

    if comiss_missoes:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=('Existem missões atribuidas a este comissionamento',),
        )

    await session.delete(db_comiss)
    await session.commit()

    return {'detail': 'Comissionamento deletado.'}
