from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session
from fcontrol_api.models.nav.aerodromos import Aerodromo
from fcontrol_api.models.public.estados_cidades import Cidade
from fcontrol_api.schemas.nav.aerodromo import (
    AerodromoCreate,
    AerodromoPublic,
    AerodromoUpdate,
)

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/aerodromos', tags=['aerodromos'])


@router.post('/', status_code=HTTPStatus.CREATED)
async def create_aerodromo(aerodromo: AerodromoCreate, session: Session):
    db_aerodromo_icao = await session.scalar(
        select(Aerodromo).where(Aerodromo.codigo_icao == aerodromo.codigo_icao)
    )

    if db_aerodromo_icao:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Código ICAO já cadastrado',
        )

    if aerodromo.codigo_iata:
        db_aerodromo_iata = await session.scalar(
            select(Aerodromo).where(
                Aerodromo.codigo_iata == aerodromo.codigo_iata
            )
        )

        if db_aerodromo_iata:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='Código ICAO já cadastrado',
            )

    base_aerea = (
        aerodromo.base_aerea.model_dump() if aerodromo.base_aerea else None
    )
    new_aerodromo = Aerodromo(
        nome=aerodromo.nome,
        codigo_icao=aerodromo.codigo_icao,
        codigo_iata=aerodromo.codigo_iata,
        latitude=aerodromo.latitude,
        longitude=aerodromo.longitude,
        elevacao=aerodromo.elevacao,
        pais=aerodromo.pais,
        utc=aerodromo.utc,
        base_aerea=base_aerea,
        codigo_cidade=aerodromo.codigo_cidade,
        cidade_manual=aerodromo.cidade_manual,
    )

    session.add(new_aerodromo)
    await session.commit()
    await session.refresh(new_aerodromo, ['cidade'])

    return new_aerodromo


@router.get('/', response_model=list[AerodromoPublic])
async def list_aerodromos(session: Session):
    aerodromos = await session.scalars(select(Aerodromo))
    return aerodromos.all()


@router.get('/{id}', response_model=AerodromoPublic)
async def get_aerodromo(id: int, session: Session):
    aerodromo = await session.scalar(
        select(Aerodromo).where(Aerodromo.id == id)
    )

    if not aerodromo:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Aeródromo não encontrado'
        )

    return aerodromo


@router.put('/{id}', response_model=AerodromoPublic)
async def update_aerodromo(
    id: int, aerodromo: AerodromoUpdate, session: Session
):
    db_aerodromo = await session.scalar(
        select(Aerodromo).where(Aerodromo.id == id)
    )

    if not db_aerodromo:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Aeródromo não encontrado'
        )

    if aerodromo.codigo_icao is not None:
        db_aerodromo_icao = await session.scalar(
            select(Aerodromo).where(
                (Aerodromo.codigo_icao == aerodromo.codigo_icao)
                & (Aerodromo.id != id)
            )
        )

        if db_aerodromo_icao:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='Código ICAO já cadastrado',
            )

    # Atualiza os campos do aeródromo
    update_data = aerodromo.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        if getattr(db_aerodromo, key) != value:
            setattr(db_aerodromo, key, value)

    await session.commit()
    await session.refresh(db_aerodromo, ['cidade'])

    return db_aerodromo


@router.delete('/{id}')
async def delete_aerodromo(id: int, session: Session):
    aerodromo = await session.scalar(
        select(Aerodromo).where(Aerodromo.id == id)
    )

    if not aerodromo:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Aeródromo não encontrado'
        )

    await session.delete(aerodromo)
    await session.commit()

    return {'detail': 'Aeródromo deletado com sucesso'}
