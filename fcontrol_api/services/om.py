"""Servicos para Ordem de Missao (OM)."""

from http import HTTPStatus

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from fcontrol_api.models.public.om import OrdemTripulacao
from fcontrol_api.models.public.tripulantes import Tripulante


async def criar_tripulacao_batch(
    session: AsyncSession, ordem_id: int, tripulacao_data
) -> None:
    """
    Cria registros de tripulacao usando batch query para evitar N+1.

    Args:
        session: Sessao do banco de dados
        ordem_id: ID da ordem de missao
        tripulacao_data: Dados da tripulacao (TripulacaoOM schema)
    """
    # Coletar todos os IDs de tripulantes
    all_trip_ids = []
    tripulacao_dict = tripulacao_data.model_dump()
    for trip_ids in tripulacao_dict.values():
        all_trip_ids.extend(trip_ids)

    if not all_trip_ids:
        return

    # Uma unica query para buscar todos os tripulantes
    tripulantes_result = await session.scalars(
        select(Tripulante)
        .where(Tripulante.id.in_(all_trip_ids))
        .options(selectinload(Tripulante.user))
    )
    tripulantes_map = {t.id: t for t in tripulantes_result.all()}

    # Criar registros de tripulacao usando o map
    for funcao, trip_ids in tripulacao_dict.items():
        for trip_id in trip_ids:
            tripulante = tripulantes_map.get(trip_id)
            if not tripulante or not tripulante.user:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=f'Tripulante {trip_id} não encontrado',
                )
            trip_ordem = OrdemTripulacao(
                ordem_id=ordem_id,
                tripulante_id=trip_id,
                funcao=funcao,
                p_g=tripulante.user.p_g,  # Snapshot do p_g atual
            )
            session.add(trip_ordem)
