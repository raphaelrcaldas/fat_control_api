from collections import defaultdict
from datetime import date
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, distinct, select, update
from sqlalchemy import func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.database import get_session
from fcontrol_api.models.instrucao.subprogramas import (
    Paop,
    PaopSubprograma,
    Subprograma,
    TripulanteSubprograma,
)
from fcontrol_api.models.shared.posto_grad import PostoGrad
from fcontrol_api.models.shared.tripulantes import Tripulante
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.instrucao.paops import (
    PaopCreate,
    PaopOut,
    PaopResumo,
    PaopSubprogramaOut,
    PaopSubprogramasSet,
    PaopTripulantesSet,
    PaopUpdate,
    TripulanteMatriculadoOut,
)
from fcontrol_api.schemas.instrucao.subprogramas import SubprogramaOut
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import ActiveOrg, permission_checker
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/paops', tags=['Instrucao'])

ViewPaop = Depends(permission_checker('instrucao-paop', 'view'))
CreatePaop = Depends(permission_checker('instrucao-paop', 'create'))
UpdatePaop = Depends(permission_checker('instrucao-paop', 'update'))
DeletePaop = Depends(permission_checker('instrucao-paop', 'delete'))


@router.get(
    '/',
    response_model=ApiResponse[list[PaopResumo]],
    dependencies=[ViewPaop],
)
async def list_paops(session: Session, active_org: ActiveOrg):
    """Planos anuais da organizacao ativa, do mais recente ao mais antigo."""
    linhas = await session.execute(
        select(
            Paop.id,
            Paop.ano,
            Paop.data_ini,
            Paop.data_fim,
            Paop.status,
            sa_func.count(distinct(PaopSubprograma.id)),
            sa_func.count(distinct(TripulanteSubprograma.id)),
        )
        .outerjoin(PaopSubprograma, PaopSubprograma.paop_id == Paop.id)
        .outerjoin(
            TripulanteSubprograma,
            TripulanteSubprograma.paop_subprograma_id == PaopSubprograma.id,
        )
        .where(Paop.uae == active_org)
        .group_by(Paop.id)
        .order_by(Paop.ano.desc())
    )

    return success_response(
        data=[
            PaopResumo(
                id=linha[0],
                ano=linha[1],
                data_ini=linha[2],
                data_fim=linha[3],
                status=linha[4],
                total_subprogramas=linha[5],
                total_matriculas=linha[6],
            )
            for linha in linhas.all()
        ]
    )


@router.post(
    '/',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[PaopResumo],
    dependencies=[CreatePaop],
)
async def create_paop(
    dados: PaopCreate,
    session: Session,
    active_org: ActiveOrg,
):
    """Abre o plano anual da organizacao ativa (um por ano)."""
    duplicado = await session.scalar(
        select(Paop.id).where(Paop.uae == active_org, Paop.ano == dados.ano)
    )
    if duplicado:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=f'Já existe PAOP para {dados.ano}',
        )

    data_ini = dados.data_ini or date(dados.ano, 1, 1)
    data_fim = dados.data_fim or date(dados.ano, 12, 31)
    if data_fim < data_ini:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='data_fim não pode ser anterior a data_ini',
        )

    paop = Paop(
        uae=active_org,
        ano=dados.ano,
        data_ini=data_ini,
        data_fim=data_fim,
        status=dados.status,
    )
    session.add(paop)
    await session.commit()
    await session.refresh(paop)

    return success_response(
        data=PaopResumo(
            id=paop.id,
            ano=paop.ano,
            data_ini=paop.data_ini,
            data_fim=paop.data_fim,
            status=paop.status,
            total_subprogramas=0,
            total_matriculas=0,
        ),
        message='PAOP criado com sucesso',
    )


@router.get(
    '/{paop_id}',
    response_model=ApiResponse[PaopOut],
    dependencies=[ViewPaop],
)
async def get_paop(paop_id: int, session: Session, active_org: ActiveOrg):
    """Plano com seus subprogramas e os tripulantes matriculados em cada um."""
    cabecalho = (
        await session.execute(
            select(
                Paop.id, Paop.ano, Paop.data_ini, Paop.data_fim, Paop.status
            ).where(Paop.id == paop_id, Paop.uae == active_org)
        )
    ).first()
    if not cabecalho:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='PAOP não encontrado'
        )

    itens = (
        await session.execute(
            select(PaopSubprograma.id, Subprograma)
            .join(
                Subprograma,
                Subprograma.id == PaopSubprograma.subprograma_id,
            )
            .where(PaopSubprograma.paop_id == paop_id)
            .order_by(Subprograma.codigo)
        )
    ).all()

    # Matrículas do plano inteiro numa consulta só, na ordem de antiguidade
    # que o resto do sistema usa para listar militares.
    matriculas = (
        await session.execute(
            select(
                TripulanteSubprograma.id,
                TripulanteSubprograma.paop_subprograma_id,
                TripulanteSubprograma.trip_id,
                TripulanteSubprograma.data_inclusao,
                Tripulante.trig,
                User.p_g,
                User.nome_guerra,
                User.nome_completo,
            )
            .join(
                PaopSubprograma,
                PaopSubprograma.id
                == TripulanteSubprograma.paop_subprograma_id,
            )
            .join(Tripulante, Tripulante.id == TripulanteSubprograma.trip_id)
            .join(User, User.id == Tripulante.user_id)
            .join(PostoGrad, PostoGrad.short == User.p_g)
            .where(PaopSubprograma.paop_id == paop_id)
            .order_by(
                PostoGrad.ant.asc(),
                User.ult_promo.asc(),
                User.ant_rel.asc(),
                User.id,
            )
        )
    ).all()

    por_item: dict[int, list[TripulanteMatriculadoOut]] = defaultdict(list)
    for m in matriculas:
        por_item[m.paop_subprograma_id].append(
            TripulanteMatriculadoOut(
                id=m.id,
                trip_id=m.trip_id,
                trig=m.trig,
                p_g=m.p_g,
                nome_guerra=m.nome_guerra,
                nome_completo=m.nome_completo,
                data_inclusao=m.data_inclusao,
            )
        )

    return success_response(
        data=PaopOut(
            id=cabecalho.id,
            ano=cabecalho.ano,
            data_ini=cabecalho.data_ini,
            data_fim=cabecalho.data_fim,
            status=cabecalho.status,
            subprogramas=[
                PaopSubprogramaOut(
                    id=item_id,
                    subprograma=SubprogramaOut.model_validate(subprograma),
                    tripulantes=por_item[item_id],
                )
                for item_id, subprograma in itens
            ],
        )
    )


@router.put(
    '/{paop_id}',
    response_model=ApiResponse[None],
    dependencies=[UpdatePaop],
)
async def update_paop(
    paop_id: int,
    dados: PaopUpdate,
    session: Session,
    active_org: ActiveOrg,
):
    """Atualiza a janela e a situacao do plano."""
    # Só o id: carregar o objeto ORM dispararia o selectin de subprogramas,
    # matrículas e tripulantes para mexer em três colunas.
    existe = await session.scalar(
        select(Paop.id).where(Paop.id == paop_id, Paop.uae == active_org)
    )
    if not existe:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='PAOP não encontrado'
        )

    if dados.data_fim < dados.data_ini:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='data_fim não pode ser anterior a data_ini',
        )

    await session.execute(
        update(Paop)
        .where(Paop.id == paop_id)
        .values(
            data_ini=dados.data_ini,
            data_fim=dados.data_fim,
            status=dados.status,
        )
    )
    await session.commit()

    return success_response(message='PAOP atualizado com sucesso')


@router.delete(
    '/{paop_id}',
    response_model=ApiResponse[None],
    dependencies=[DeletePaop],
)
async def delete_paop(paop_id: int, session: Session, active_org: ActiveOrg):
    """Remove um plano que ainda nao tem tripulante matriculado."""
    paop = await session.scalar(
        select(Paop).where(Paop.id == paop_id, Paop.uae == active_org)
    )
    if not paop:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='PAOP não encontrado'
        )

    matriculados = await session.scalar(
        select(sa_func.count(TripulanteSubprograma.id))
        .join(
            PaopSubprograma,
            PaopSubprograma.id == TripulanteSubprograma.paop_subprograma_id,
        )
        .where(PaopSubprograma.paop_id == paop_id)
    )
    if matriculados:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=(
                'PAOP com tripulante matriculado não pode ser removido '
                f'({matriculados} matrícula(s))'
            ),
        )

    await session.delete(paop)
    await session.commit()

    return success_response(message='PAOP removido com sucesso')


@router.put(
    '/{paop_id}/subprogramas',
    response_model=ApiResponse[None],
    dependencies=[UpdatePaop],
)
async def set_paop_subprogramas(
    paop_id: int,
    dados: PaopSubprogramasSet,
    session: Session,
    active_org: ActiveOrg,
):
    """Define quais subprogramas compoem o plano."""
    paop = await session.scalar(
        select(Paop.id).where(Paop.id == paop_id, Paop.uae == active_org)
    )
    if not paop:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='PAOP não encontrado'
        )

    desejados = set(dados.subprograma_ids)

    # Só subprograma da própria unidade entra no plano dela.
    if desejados:
        validos = set(
            (
                await session.scalars(
                    select(Subprograma.id).where(
                        Subprograma.id.in_(desejados),
                        Subprograma.uae == active_org,
                    )
                )
            ).all()
        )
        if validos != desejados:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='Subprograma inexistente na organização',
            )

    atuais = {
        item_id: subprograma_id
        for item_id, subprograma_id in (
            await session.execute(
                select(
                    PaopSubprograma.id, PaopSubprograma.subprograma_id
                ).where(PaopSubprograma.paop_id == paop_id)
            )
        ).all()
    }

    remover = [
        item_id
        for item_id, subprograma_id in atuais.items()
        if subprograma_id not in desejados
    ]
    if remover:
        em_uso = (
            await session.execute(
                select(
                    TripulanteSubprograma.paop_subprograma_id,
                    sa_func.count(TripulanteSubprograma.id),
                )
                .where(TripulanteSubprograma.paop_subprograma_id.in_(remover))
                .group_by(TripulanteSubprograma.paop_subprograma_id)
            )
        ).all()
        if em_uso:
            codigos = (
                await session.scalars(
                    select(Subprograma.codigo)
                    .join(
                        PaopSubprograma,
                        PaopSubprograma.subprograma_id == Subprograma.id,
                    )
                    .where(
                        PaopSubprograma.id.in_([linha[0] for linha in em_uso])
                    )
                    .order_by(Subprograma.codigo)
                )
            ).all()
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=(
                    'Subprograma com tripulante matriculado não sai do '
                    f'plano: {", ".join(codigos)}'
                ),
            )

        await session.execute(
            delete(PaopSubprograma).where(PaopSubprograma.id.in_(remover))
        )

    for subprograma_id in desejados - set(atuais.values()):
        session.add(
            PaopSubprograma(paop_id=paop_id, subprograma_id=subprograma_id)
        )

    await session.commit()

    return success_response(message='Subprogramas do PAOP atualizados')


@router.put(
    '/{paop_id}/subprogramas/{item_id}/tripulantes',
    response_model=ApiResponse[None],
    dependencies=[UpdatePaop],
)
async def set_item_tripulantes(
    paop_id: int,
    item_id: int,
    dados: PaopTripulantesSet,
    session: Session,
    active_org: ActiveOrg,
):
    """Define os tripulantes matriculados num subprograma do plano."""
    item = (
        await session.execute(
            select(PaopSubprograma.id, Subprograma.func)
            .join(Paop, Paop.id == PaopSubprograma.paop_id)
            .join(
                Subprograma,
                Subprograma.id == PaopSubprograma.subprograma_id,
            )
            .where(
                PaopSubprograma.id == item_id,
                PaopSubprograma.paop_id == paop_id,
                Paop.uae == active_org,
            )
        )
    ).first()
    if not item:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Subprograma não encontrado neste PAOP',
        )

    desejados = set(dados.trip_ids)

    atuais = set(
        (
            await session.scalars(
                select(TripulanteSubprograma.trip_id).where(
                    TripulanteSubprograma.paop_subprograma_id == item_id
                )
            )
        ).all()
    )

    # Matrícula exige tripulante ativo da unidade E da função do subprograma:
    # um SPFO de piloto não matricula mecânico. A regra vale para quem ESTÁ
    # ENTRANDO — quem já estava matriculado permanece mesmo se depois for
    # inativado ou trocar de função, senão o item ficaria ineditável (o
    # payload de reconciliação carrega o vínculo velho junto).
    novos = desejados - atuais
    if novos:
        validos = set(
            (
                await session.scalars(
                    select(Tripulante.id).where(
                        Tripulante.id.in_(novos),
                        Tripulante.uae == active_org,
                        Tripulante.active.is_(True),
                        Tripulante.func == item.func,
                    )
                )
            ).all()
        )
        if validos != novos:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=(
                    'Tripulante inativo, de outra organização ou de função '
                    'diferente da do subprograma'
                ),
            )

    remover = atuais - desejados
    if remover:
        await session.execute(
            delete(TripulanteSubprograma).where(
                TripulanteSubprograma.paop_subprograma_id == item_id,
                TripulanteSubprograma.trip_id.in_(remover),
            )
        )

    hoje = date.today()
    for trip_id in novos:
        session.add(
            TripulanteSubprograma(
                paop_subprograma_id=item_id,
                trip_id=trip_id,
                data_inclusao=hoje,
            )
        )

    await session.commit()

    return success_response(message='Matrículas atualizadas')
