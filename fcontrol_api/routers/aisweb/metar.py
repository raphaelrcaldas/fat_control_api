from http import HTTPStatus

import defusedxml.ElementTree as ET
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from fcontrol_api.routers.aisweb.client import aisweb_client
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.utils.responses import success_response

router = APIRouter(prefix='/met', tags=['AISWEB'])


class MetData(BaseModel):
    metar: str
    taf: str | None = None


def _clean(raw: str | None, prefix: str) -> str | None:
    if not raw:
        return None
    text = raw.strip().removeprefix(prefix).rstrip('=').strip()
    return text or None


@router.get(
    '/{icao}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[MetData],
)
async def get_met(icao: str):
    try:
        async with aisweb_client() as client:
            response = await client.get(
                '',
                params={
                    'area': 'met',
                    'icaoCode': icao.upper(),
                },
            )
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
        metar_raw = _clean(root.findtext('.//metar'), 'METAR ')
        taf_raw = _clean(root.findtext('.//taf'), 'TAF ')
    except ET.ParseError:
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail='Resposta inválida do AISWEB',
        )

    if not metar_raw:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f'METAR não encontrado para {icao.upper()}',
        )

    return success_response(data=MetData(metar=metar_raw, taf=taf_raw))
