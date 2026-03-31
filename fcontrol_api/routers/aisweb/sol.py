from http import HTTPStatus
from typing import Annotated

import defusedxml.ElementTree as ET
import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from fcontrol_api.routers.aisweb.client import aisweb_client
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.utils.responses import success_response

router = APIRouter(prefix='/sol', tags=['AISWEB'])


class SolData(BaseModel):
    date: str
    sunrise: str
    sunset: str
    weekday: int
    aero: str


@router.get(
    '/{icao}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[list[SolData]],
)
async def get_sol(
    icao: str,
    dt_i: Annotated[
        str | None, Query(description='Data inicial YYYY-MM-DD')
    ] = None,
    dt_f: Annotated[
        str | None, Query(description='Data final YYYY-MM-DD')
    ] = None,
):
    params: dict[str, str] = {'area': 'sol', 'icaoCode': icao.upper()}
    if dt_i:
        params['dt_i'] = dt_i
    if dt_f:
        params['dt_f'] = dt_f

    try:
        async with aisweb_client() as client:
            response = await client.get('', params=params)
            response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail=f'AISWEB retornou HTTP {e.response.status_code}',
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail='Falha ao conectar ao AISWEB',
        )

    try:
        root = ET.fromstring(response.text)
        items = root.findall('.//day')
    except ET.ParseError:
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail='Resposta inválida do AISWEB',
        )

    result: list[SolData] = []
    for item in items:
        date = item.findtext('date') or ''
        sunrise = item.findtext('sunrise') or ''
        sunset = item.findtext('sunset') or ''
        weekday_txt = item.findtext('weekDay') or '0'
        aero = item.findtext('aero') or icao.upper()
        if date and sunrise and sunset:
            try:
                weekday = int(weekday_txt)
            except ValueError:
                weekday = 0
            result.append(
                SolData(
                    date=date,
                    sunrise=sunrise,
                    sunset=sunset,
                    weekday=weekday,
                    aero=aero,
                )
            )

    if not result:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f'Dados de sol não encontrados para {icao.upper()}',
        )

    return success_response(data=result)
