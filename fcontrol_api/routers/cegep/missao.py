from datetime import date, datetime, time
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.diarias import GrupoCidade, GrupoPg
from fcontrol_api.models.cegep.missoes import FragMis, PernoiteFrag, UserFrag
from fcontrol_api.models.public.estados_cidades import Cidade
from fcontrol_api.models.public.users import User
from fcontrol_api.schemas.custos import (
    CustoFragMisInput,
    CustoPernoiteInput,
    CustoUserFragInput,
)
from fcontrol_api.schemas.missoes import (
    FragMisSchema,
    PernoiteFragMis,
    UserFragMis,
)
from fcontrol_api.services.comis import (
    recalcular_comiss_afetados,
    verificar_usrs_comiss,
)
from fcontrol_api.services.financeiro import cache_diarias, cache_soldos
from fcontrol_api.services.missao import adicionar_missao, verificar_conflitos
from fcontrol_api.utils.financeiro import calcular_custos_frag_mis

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/missoes', tags=['CEGEP'])


@router.get('/', response_model=list[FragMisSchema])
async def get_fragmentos(
    session: Session,
    tipo_doc: str = None,
    n_doc: int = None,
    tipo: str = None,
    user_search: str = None,
    city: str = None,
    ini: date = None,
    fim: date = None,
):
    ini = datetime.combine(ini, time(0, 0, 0))
    fim = datetime.combine(fim, time(23, 59, 59))

    stmt = (
        select(FragMis)
        .options(selectinload(FragMis.users))
        .filter(FragMis.afast >= ini, FragMis.regres <= fim)
        .order_by(FragMis.afast.desc())
    )

    if tipo_doc:
        stmt = stmt.where(FragMis.tipo_doc == tipo_doc)

    if n_doc:
        stmt = stmt.where(FragMis.n_doc == n_doc)

    if tipo:
        stmt = stmt.where(FragMis.tipo == tipo)

    if city:
        stmt = (
            stmt.join(PernoiteFrag)
            .join(Cidade)
            .where(Cidade.nome.ilike(f'%{city}%'))
        )

    if user_search:
        stmt = (
            stmt.join(UserFrag)
            .join(User)
            .where(User.nome_guerra.ilike(f'%{user_search}%'))
        )

    db_frags = (await session.scalars(stmt)).unique().all()

    # Ordena os usuários dentro de cada missão
    for frag in db_frags:
        frag.users.sort(
            key=lambda u: (
                u.user.posto.ant,
                u.user.ult_promo or date.min,
                u.user.ant_rel or 0,
            )
        )

    return db_frags


@router.post('/')
async def create_or_update_missao(payload: FragMisSchema, session: Session):
    missao = await adicionar_missao(payload, session)

    await verificar_conflitos(payload, session)

    await verificar_usrs_comiss(
        [u for u in payload.users if u.sit == 'c'],
        payload.afast,
        payload.regres,
        session,
    )

    # Adiciona pernoites e prepara inputs validados
    pernoites_input: list[CustoPernoiteInput] = []
    for p in payload.pernoites:
        pnt_data = PernoiteFragMis.model_validate(p).model_dump(
            exclude={'cidade', 'id', 'frag_id'}
        )
        pernoite = PernoiteFrag(**pnt_data, frag_id=missao.id)
        session.add(pernoite)
        await session.flush()  # Flush para obter o ID do pernoite

        # Criar input validado com Pydantic
        pernoite_input = CustoPernoiteInput(
            id=pernoite.id,
            data_ini=pernoite.data_ini,
            data_fim=pernoite.data_fim,
            meia_diaria=pernoite.meia_diaria,
            acrec_desloc=pernoite.acrec_desloc,
            cidade_codigo=p.cidade.codigo,  # Extrai código diretamente
        )
        pernoites_input.append(pernoite_input)

    # Adiciona militares e prepara inputs validados
    users_frag_input: list[CustoUserFragInput] = []
    for u in payload.users:
        user_data = UserFragMis.model_validate(u).model_dump(
            exclude={'user', 'id', 'frag_id'}
        )
        session.add(UserFrag(**user_data, frag_id=missao.id))

        # Criar input validado com Pydantic
        user_input = CustoUserFragInput(
            p_g=user_data['p_g'],
            sit=user_data['sit'],
        )
        users_frag_input.append(user_input)

    # Carregar caches necessários para cálculo de custos
    valores_cache = await cache_diarias(session)
    soldos_cache = await cache_soldos(session)

    # Carregar grupos_pg e grupos_cidade
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

    # Criar input validado da missão
    frag_mis_input = CustoFragMisInput(acrec_desloc=missao.acrec_desloc)

    # Calcular custos com inputs validados e tipados
    custos = calcular_custos_frag_mis(
        frag_mis_input,
        users_frag_input,
        pernoites_input,
        grupos_pg,
        grupos_cidade,
        valores_cache,
        soldos_cache,
    )

    # Atualizar campo custos na missão
    missao.custos = custos

    # Recalcular cache dos comissionamentos afetados
    for u in payload.users:
        if u.sit == 'c':
            await recalcular_comiss_afetados(
                u.user_id,
                payload.afast.date()
                if hasattr(payload.afast, 'date')
                else payload.afast,
                payload.regres.date()
                if hasattr(payload.regres, 'date')
                else payload.regres,
                session,
            )

    await session.commit()

    return {'detail': 'Missão salva com sucesso'}


@router.delete('/{id}')
async def delete_fragmis(id: int, session: Session):
    db_frag = await session.scalar(
        select(FragMis)
        .options(selectinload(FragMis.users))
        .where((FragMis.id == id))
    )
    if not db_frag:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Missão não encontrada',
        )

    # Guardar dados antes de deletar para recalcular comissionamentos
    comiss_users = [
        (u.user_id, db_frag.afast.date(), db_frag.regres.date())
        for u in db_frag.users
        if u.sit == 'c'
    ]

    await session.execute(
        delete(PernoiteFrag).where(PernoiteFrag.frag_id == id)
    )
    await session.execute(delete(UserFrag).where(UserFrag.frag_id == id))

    await session.delete(db_frag)

    # Recalcular cache dos comissionamentos afetados após deletar
    for user_id, afast, regres in comiss_users:
        await recalcular_comiss_afetados(user_id, afast, regres, session)

    await session.commit()

    return {'detail': 'Missão removida com sucesso'}
