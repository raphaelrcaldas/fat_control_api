from datetime import date, timedelta
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.cegep.missoes import FragMis, PernoiteFrag, UserFrag
from fcontrol_api.models.shared.posto_grad import PostoGrad, Soldo
from fcontrol_api.schemas.cegep.soldo import (
    SoldoCreate,
    SoldoPublic,
    SoldoStats,
    SoldoUpdate,
)
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.services.missao import recalcular_custos_missoes
from fcontrol_api.services.vigencia import garantir_sem_sobreposicao
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]

# Tabela de soldos (referência financeira nacional): control-plane de
# sistema. O gate `require_system_admin` é aplicado uma única vez no grupo
# admin (routers/admin/__init__.py) — este router não repete a dependência.
#
# Todo recálculo aqui vai com `afeta_comiss=False`: soldo só entra no
# cálculo de `sit='g'` (gratificação de representação), e o cache do
# comissionamento lê só `sit='c'`. Diárias, que afetam os dois, mantêm o
# padrão. Ver `recalcular_custos_missoes`.
router = APIRouter(prefix='/soldos', tags=['Admin - Soldos'])


def _janela_recalculo(
    db_soldo: Soldo, update_data: dict
) -> tuple[date, date | None] | None:
    """Menor janela de datas cujas missões podem ter mudado de custo.

    Recalcular a união das vigências (antiga ∪ nova) é caro sem
    necessidade: editar a `data_fim` de um soldo que vige desde 2019
    varreria seis anos de missões, quando só o trecho entre o fim antigo
    e o novo troca de soldo. Aqui a janela é o **delta**:

    - `valor`/`pg`: a vigência inteira muda de valor;
    - `data_inicio`/`data_fim`: só o trecho entre a data antiga e a nova;
    - fim que vira NULL (ou deixa de ser): trecho aberto a partir da data
      conhecida — sem isso o recálculo parava no fim antigo e as missões
      posteriores ficavam com o custo do soldo seguinte.

    Retorna None quando nada que afete custo mudou.
    """
    old_inicio, old_fim = db_soldo.data_inicio, db_soldo.data_fim
    new_inicio = update_data.get('data_inicio', old_inicio)
    new_fim = update_data.get('data_fim', old_fim)

    mudou_chave = (
        update_data.get('pg', db_soldo.pg) != db_soldo.pg
        or update_data.get('valor', db_soldo.valor) != db_soldo.valor
    )
    if mudou_chave:
        fim = (
            None
            if old_fim is None or new_fim is None
            else max(old_fim, new_fim)
        )
        return min(old_inicio, new_inicio), fim

    trechos: list[tuple[date, date | None]] = []
    if new_inicio != old_inicio:
        trechos.append((
            min(old_inicio, new_inicio),
            max(old_inicio, new_inicio),
        ))
    if new_fim != old_fim:
        if old_fim is None or new_fim is None:
            trechos.append((old_fim or new_fim, None))
        else:
            trechos.append((min(old_fim, new_fim), max(old_fim, new_fim)))

    if not trechos:
        return None

    inicio = min(t[0] for t in trechos)
    fim = (
        None
        if any(t[1] is None for t in trechos)
        else max(t[1] for t in trechos)
    )
    return inicio, fim


@router.get(
    '/stats',
    response_model=ApiResponse[SoldoStats],
)
async def get_soldo_stats(
    session: Session,
    circulo: str | None = Query(None, description='Filtrar por circulo'),
):
    """Retorna estatisticas dos soldos"""
    query = select(
        func.count(Soldo.id),
        func.min(Soldo.valor),
        func.max(Soldo.valor),
    )

    if circulo:
        query = query.join(PostoGrad).where(PostoGrad.circulo == circulo)

    result = await session.execute(query)
    row = result.one()

    return success_response(
        data=SoldoStats(
            total=row[0] or 0,
            min_valor=row[1],
            max_valor=row[2],
        )
    )


@router.get(
    '/',
    response_model=ApiResponse[list[SoldoPublic]],
)
async def list_soldos(
    session: Session,
    circulo: str | None = Query(None, description='Filtrar por circulo'),
    active_only: bool = Query(False, description='Apenas soldos vigentes'),
):
    """Lista todos os soldos com filtros opcionais"""
    query = select(Soldo)

    if circulo:
        query = query.join(PostoGrad).where(PostoGrad.circulo == circulo)

    if active_only:
        today = date.today()
        query = query.where(
            and_(
                Soldo.data_inicio <= today,
                or_(Soldo.data_fim.is_(None), Soldo.data_fim >= today),
            )
        )

    query = query.order_by(Soldo.data_inicio.desc())

    result = await session.scalars(query)
    return success_response(data=list(result.all()))


@router.get(
    '/{soldo_id}',
    response_model=ApiResponse[SoldoPublic],
)
async def get_soldo(soldo_id: int, session: Session):
    """Busca um soldo por ID"""
    soldo = await session.scalar(select(Soldo).where(Soldo.id == soldo_id))

    if not soldo:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Soldo nao encontrado',
        )

    return success_response(data=soldo)


@router.post(
    '/',
    status_code=HTTPStatus.CREATED,
    response_model=ApiResponse[SoldoPublic],
)
async def create_soldo(soldo: SoldoCreate, session: Session):
    """Cria um novo registro de soldo"""
    if soldo.data_fim and soldo.data_fim <= soldo.data_inicio:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Data fim deve ser maior que data inicio',
        )

    posto = await session.scalar(
        select(PostoGrad).where(PostoGrad.short == soldo.pg)
    )

    if not posto:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Posto/Graduacao invalido',
        )

    # Auto-fechar periodo anterior ativo (mesmo pg)
    anterior = await session.scalar(
        select(Soldo).where(
            and_(
                Soldo.pg == soldo.pg,
                Soldo.data_fim.is_(None),
            )
        )
    )

    if anterior:
        nova_data_fim = soldo.data_inicio - timedelta(days=1)
        if nova_data_fim < anterior.data_inicio:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=(
                    'Novo soldo comeca antes do soldo vigente '
                    f'(inicio: {anterior.data_inicio})'
                ),
            )
        anterior.data_fim = nova_data_fim

    # Rede de seguranca contra faixas sobrepostas para o mesmo pg (o
    # auto-close acima ja fechou o periodo aberto; aqui barramos qualquer
    # outra faixa que ainda conflite com o periodo informado).
    await garantir_sem_sobreposicao(
        session,
        Soldo,
        [Soldo.pg == soldo.pg],
        soldo.data_inicio,
        soldo.data_fim,
    )

    new_soldo = Soldo(
        pg=soldo.pg,
        data_inicio=soldo.data_inicio,
        data_fim=soldo.data_fim,
        valor=soldo.valor,
    )

    session.add(new_soldo)
    await session.flush()

    await recalcular_custos_missoes(
        soldo.data_inicio, soldo.data_fim, session, afeta_comiss=False
    )

    await session.commit()
    await session.refresh(new_soldo)

    return success_response(
        data=SoldoPublic.model_validate(new_soldo),
        message='Soldo criado com sucesso',
    )


@router.put(
    '/{soldo_id}',
    response_model=ApiResponse[SoldoPublic],
)
async def update_soldo(soldo_id: int, soldo: SoldoUpdate, session: Session):
    """Atualiza um soldo existente"""
    db_soldo = await session.scalar(select(Soldo).where(Soldo.id == soldo_id))

    if not db_soldo:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Soldo nao encontrado',
        )

    update_data = soldo.model_dump(exclude_unset=True)

    # Janela calculada ANTES do setattr (precisa dos valores atuais) e
    # comparando com o banco, não por `exclude_unset`: o formulário do
    # front reenvia os quatro campos a cada submit.
    janela = _janela_recalculo(db_soldo, update_data)

    # Valida datas
    data_inicio = update_data.get('data_inicio', db_soldo.data_inicio)
    data_fim = update_data.get('data_fim', db_soldo.data_fim)
    if data_fim and data_fim <= data_inicio:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Data fim deve ser maior que data inicio',
        )

    if 'pg' in update_data:
        posto = await session.scalar(
            select(PostoGrad).where(PostoGrad.short == update_data['pg'])
        )
        if not posto:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='Posto/Graduacao invalido',
            )

    # So checamos sobreposicao quando a faixa (chave ou datas) muda; uma
    # edicao apenas de `valor` nao desloca o periodo e nao pode criar
    # conflito novo.
    if {'pg', 'data_inicio', 'data_fim'} & update_data.keys():
        pg_efetivo = update_data.get('pg', db_soldo.pg)
        await garantir_sem_sobreposicao(
            session,
            Soldo,
            [Soldo.pg == pg_efetivo],
            data_inicio,
            data_fim,
            excluir_id=soldo_id,
        )

    for key, value in update_data.items():
        setattr(db_soldo, key, value)

    await session.flush()

    if janela is not None:
        await recalcular_custos_missoes(*janela, session, afeta_comiss=False)

    await session.commit()
    await session.refresh(db_soldo)

    return success_response(
        data=SoldoPublic.model_validate(db_soldo),
        message='Soldo atualizado com sucesso',
    )


@router.delete(
    '/{soldo_id}',
    response_model=ApiResponse[None],
)
async def delete_soldo(soldo_id: int, session: Session):
    """Deleta um registro de soldo"""
    db_soldo = await session.scalar(select(Soldo).where(Soldo.id == soldo_id))

    if not db_soldo:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Soldo nao encontrado',
        )

    # Verificar se ha missoes com UserFrag sit='g' no periodo
    query_check = (
        select(UserFrag.id)
        .join(FragMis, FragMis.id == UserFrag.frag_id)
        .join(PernoiteFrag, PernoiteFrag.frag_id == FragMis.id)
        .where(
            UserFrag.sit == 'g',
            PernoiteFrag.data_fim >= db_soldo.data_inicio,
        )
    )
    if db_soldo.data_fim is not None:
        query_check = query_check.where(
            PernoiteFrag.data_ini <= db_soldo.data_fim
        )

    missao_vinculada = await session.scalar(query_check.limit(1))
    if missao_vinculada:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=(
                'Não é possível deletar: existem missões com '
                'gratificação de representação no período '
                'deste soldo'
            ),
        )

    # Guardar datas antes de deletar
    del_inicio = db_soldo.data_inicio
    del_fim = db_soldo.data_fim

    await session.delete(db_soldo)
    await session.flush()

    await recalcular_custos_missoes(
        del_inicio, del_fim, session, afeta_comiss=False
    )

    await session.commit()

    return success_response(message='Soldo deletado com sucesso')
