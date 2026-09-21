"""Router das localidades especiais (GLE).

**Tabela global, sem escopo de organizacao.** A classificacao GLE e
nacional e `grupos_loc_esp` nao tem coluna de org: filtrar por
`ActiveOrg` seria inventar um escopo que o dado nao tem. O gate de RBAC
continua valendo — o que e global e o dado, nao o acesso.

Contexto de dominio em `docs/dominio/gle.md`.
"""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import func as sql_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fcontrol_api.database import get_session
from fcontrol_api.models.shared.estados_cidades import (
    Cidade,
    GrupoLocEsp,
    LocEspIcao,
)
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.cegep.gle import (
    LocEspCreate,
    LocEspOut,
    LocEspUpdate,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import (
    get_current_user,
    permission_checker,
)
from fcontrol_api.services.gle.auditoria import snapshot_localidade
from fcontrol_api.services.gle.leitura import montar_localidade
from fcontrol_api.services.gle.localidades import (
    atualizar_localidade,
    criar_localidade,
)
from fcontrol_api.services.logs import log_user_action
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

LocEspId = Annotated[int, Path()]

router = APIRouter(prefix='/gle', tags=['CEGEP'])

RESOURCE_GLE = 'loc_esp'

ViewGle = Depends(permission_checker('cegep.gle', 'view'))
CreateGle = Depends(permission_checker('cegep.gle', 'create'))
UpdateGle = Depends(permission_checker('cegep.gle', 'update'))
DeleteGle = Depends(permission_checker('cegep.gle', 'delete'))


@router.get(
    '',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[list[LocEspOut]],
    dependencies=[ViewGle],
)
async def list_localidades(
    session: Session,
    grupo: Annotated[int | None, Query(ge=1, le=2)] = None,
    uf: Annotated[str | None, Query(max_length=2)] = None,
    search: Annotated[str | None, Query()] = None,
) -> ApiResponse[list[LocEspOut]]:
    """Lista as localidades especiais.

    Sem paginacao: sao poucas dezenas de municipios no pais inteiro, e a
    tela precisa do conjunto todo para filtrar no cliente.

    `search` casa nome da cidade (sem acento) ou ICAO.
    """
    stmt = (
        select(GrupoLocEsp)
        .join(Cidade, Cidade.codigo == GrupoLocEsp.cidade_id)
        .options(
            selectinload(GrupoLocEsp.cidade),
            selectinload(GrupoLocEsp.icaos),
        )
        .order_by(Cidade.nome, GrupoLocEsp.id)
    )

    if grupo is not None:
        stmt = stmt.where(GrupoLocEsp.grupo == grupo)
    if uf:
        stmt = stmt.where(Cidade.uf == uf.upper())
    if search:
        termo = search.strip()
        # "Contém", como na cidade: o campo é um só ("Município ou
        # ICAO..."), e com prefixo digitar "BEG" não acharia SBEG — o
        # usuário concluiria que o ICAO não está cadastrado.
        por_icao = select(LocEspIcao.loc_esp_id).where(
            LocEspIcao.icao.ilike(f'%{termo}%')
        )
        stmt = stmt.where(
            sql_func.unaccent(Cidade.nome).ilike(
                sql_func.unaccent(f'%{termo}%')
            )
            | GrupoLocEsp.id.in_(por_icao)
        )

    localidades = (await session.scalars(stmt)).all()
    return success_response(
        data=[montar_localidade(loc) for loc in localidades]
    )


@router.get(
    '/{id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[LocEspOut],
    dependencies=[ViewGle],
)
async def get_localidade(
    id: LocEspId, session: Session
) -> ApiResponse[LocEspOut]:
    loc = await session.scalar(
        select(GrupoLocEsp)
        .options(
            selectinload(GrupoLocEsp.cidade),
            selectinload(GrupoLocEsp.icaos),
        )
        .where(GrupoLocEsp.id == id)
    )
    if not loc:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Localidade não encontrada',
        )
    return success_response(data=montar_localidade(loc))


@router.post(
    '',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[LocEspOut],
    dependencies=[CreateGle],
)
async def create_localidade(
    data: LocEspCreate, session: Session, current_user: CurrentUser
) -> ApiResponse[LocEspOut]:
    loc = await criar_localidade(session, data)

    await log_user_action(
        session=session,
        user_id=current_user.id,
        action='create',
        resource=RESOURCE_GLE,
        resource_id=loc.id,
        before=None,
        after=snapshot_localidade(loc),
    )

    saida = montar_localidade(loc)
    await session.commit()
    return success_response(
        data=saida,
        message='Localidade especial criada com sucesso',
    )


@router.put(
    '/{id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[LocEspOut],
    dependencies=[UpdateGle],
)
async def update_localidade(
    id: LocEspId,
    data: LocEspUpdate,
    session: Session,
    current_user: CurrentUser,
) -> ApiResponse[LocEspOut]:
    """Atualiza a localidade. Os ICAOs enviados substituem os atuais."""
    loc = await session.scalar(
        select(GrupoLocEsp)
        .options(
            selectinload(GrupoLocEsp.cidade),
            selectinload(GrupoLocEsp.icaos),
        )
        .where(GrupoLocEsp.id == id)
    )
    if not loc:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Localidade não encontrada',
        )

    before = snapshot_localidade(loc)

    await atualizar_localidade(session, loc, data)
    after = snapshot_localidade(loc)

    if before != after:
        await log_user_action(
            session=session,
            user_id=current_user.id,
            action='update',
            resource=RESOURCE_GLE,
            resource_id=loc.id,
            before=before,
            after=after,
        )

    saida = montar_localidade(loc)
    await session.commit()
    return success_response(
        data=saida,
        message='Localidade especial atualizada com sucesso',
    )


@router.delete(
    '/{id}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[None],
    dependencies=[DeleteGle],
)
async def delete_localidade(
    id: LocEspId, session: Session, current_user: CurrentUser
) -> ApiResponse[None]:
    """Remove a localidade. Os ICAOs vao junto (CASCADE no banco)."""
    loc = await session.scalar(
        select(GrupoLocEsp)
        .options(
            selectinload(GrupoLocEsp.cidade),
            selectinload(GrupoLocEsp.icaos),
        )
        .where(GrupoLocEsp.id == id)
    )
    if not loc:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Localidade não encontrada',
        )

    before = snapshot_localidade(loc)
    await session.delete(loc)

    await log_user_action(
        session=session,
        user_id=current_user.id,
        action='delete',
        resource=RESOURCE_GLE,
        resource_id=id,
        before=before,
        after=None,
    )

    await session.commit()
    return success_response(message='Localidade especial removida com sucesso')
