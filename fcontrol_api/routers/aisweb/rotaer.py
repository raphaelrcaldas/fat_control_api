from http import HTTPStatus
from typing import Annotated

import defusedxml.ElementTree as ET
import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from fcontrol_api.routers.aisweb.client import aisweb_client
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.utils.responses import success_response

router = APIRouter(prefix='/rotaer', tags=['AISWEB'])


class RotaerOrg(BaseModel):
    name: str | None
    type: str | None
    military: bool | None


class RotaerRunway(BaseModel):
    type: str | None
    ident: str | None
    surface: str | None
    length_m: int | None
    width_m: int | None
    surface_c: str | None
    lights: list[str]


class RotaerService(BaseModel):
    service_type: str
    raw_xml: str


class RotaerData(BaseModel):
    status: str | None
    dt: str | None
    icao: str | None
    ciad: str | None
    name: str | None
    city: str | None
    uf: str | None
    lat: float | None
    lng: float | None
    lat_rotaer: str | None
    lng_rotaer: str | None
    distance: str | None
    org: RotaerOrg | None
    working_hour: str | None
    type: str | None
    type_util: str | None
    type_opr: str | None
    cat: str | None
    utc: str | None
    alt_m: float | None
    alt_ft: float | None
    fir: str | None
    jur: str | None
    lights: list[str]
    runways: list[RotaerRunway]
    services: list[RotaerService]
    remarks: list[str]
    complements: dict[str, str]


class RotaerResponse(BaseModel):
    data: RotaerData | None = None
    rotaer_html: str | None = None


def _parse_int(text: str | None) -> int | None:
    if not text:
        return None
    try:
        return int(text.strip())
    except ValueError:
        return None


def _parse_float(text: str | None) -> float | None:
    if not text:
        return None
    try:
        return float(text.strip())
    except ValueError:
        return None


def _parse_military(text: str | None) -> bool | None:
    if not text:
        return None
    upper = text.strip().upper()
    if upper in {'MILITAR', 'MIL', 'S'}:
        return True
    if upper in {'CIVIL', 'N'}:
        return False
    return None


def _collect_lights(elem: ET.Element) -> list[str]:
    """Coleta descr de todas as tags <lights>/<light> dentro de elem."""
    result: list[str] = []
    for lights_elem in elem.findall('lights'):
        for light in lights_elem.findall('light'):
            descr = light.get('descr', '').strip()
            if descr:
                result.append(descr)
    return result


def _parse_runways(root: ET.Element) -> list[RotaerRunway]:
    runways_elem = root.find('runways')
    if runways_elem is None:
        return []

    result: list[RotaerRunway] = []
    for rwy in runways_elem.findall('runway'):
        surface_elem = rwy.find('surface')
        surface_text = (
            surface_elem.text.strip()
            if surface_elem is not None and surface_elem.text
            else None
        )

        surface_c_elem = rwy.find('surface_c')
        surface_c = (
            surface_c_elem.text.strip()
            if surface_c_elem is not None and surface_c_elem.text
            else None
        )

        length_elem = rwy.find('length')
        length_m = _parse_int(
            length_elem.text if length_elem is not None else None
        )

        width_elem = rwy.find('width')
        width_m = _parse_int(
            width_elem.text if width_elem is not None else None
        )

        result.append(
            RotaerRunway(
                type=rwy.findtext('type'),
                ident=rwy.findtext('ident'),
                surface=surface_text,
                length_m=length_m,
                width_m=width_m,
                surface_c=surface_c,
                lights=_collect_lights(rwy),
            )
        )

    return result


def _parse_services(root: ET.Element) -> list[RotaerService]:
    services_elem = root.find('services')
    if services_elem is None:
        return []

    result: list[RotaerService] = []
    for svc in services_elem.findall('service'):
        service_type = svc.get('type', '')
        raw_xml = ET.tostring(svc, encoding='unicode')
        result.append(
            RotaerService(service_type=service_type, raw_xml=raw_xml)
        )

    return result


def _parse_remarks(root: ET.Element) -> list[str]:
    rmk_elem = root.find('rmk')
    if rmk_elem is None:
        return []
    return [
        elem.text.strip()
        for elem in rmk_elem.findall('rmkText')
        if elem.text and elem.text.strip()
    ]


def _parse_complements(root: ET.Element) -> dict[str, str]:
    compls_elem = root.find('compls')
    if compls_elem is None:
        return {}

    result: dict[str, str] = {}
    for compl in compls_elem.findall('compl'):
        cod = compl.get('cod', '')
        n = compl.get('n', '')
        key = f'{cod}_{n}'
        result[key] = (compl.text or '').strip()

    return result


def _parse_org(root: ET.Element) -> RotaerOrg | None:
    org_elem = root.find('org')
    if org_elem is None:
        return None

    raw_name = org_elem.findtext('name')
    return RotaerOrg(
        name=raw_name.strip() if raw_name else None,
        type=org_elem.findtext('type'),
        military=_parse_military(org_elem.findtext('military')),
    )


def _parse_rotaer_xml(root: ET.Element, icao: str) -> RotaerData:
    return RotaerData(
        status=root.findtext('status'),
        dt=root.findtext('dt'),
        icao=root.findtext('AeroCode') or icao.upper(),
        ciad=root.findtext('ciad'),
        name=(root.findtext('name') or '').strip() or None,
        city=root.findtext('city'),
        uf=root.findtext('uf'),
        lat=_parse_float(root.findtext('lat')),
        lng=_parse_float(root.findtext('lng')),
        lat_rotaer=(root.findtext('latRotaer') or '').strip() or None,
        lng_rotaer=(root.findtext('lngRotaer') or '').strip() or None,
        distance=root.findtext('distance'),
        org=_parse_org(root),
        working_hour=root.findtext('workinghour'),
        type=root.findtext('type'),
        type_util=root.findtext('typeUtil'),
        type_opr=root.findtext('typeOpr'),
        cat=root.findtext('cat'),
        utc=root.findtext('utc'),
        alt_m=_parse_float(root.findtext('altM')),
        alt_ft=_parse_float(root.findtext('altFt')),
        fir=root.findtext('fir'),
        jur=(root.findtext('jur') or '').strip() or None,
        lights=_collect_lights(root),
        runways=_parse_runways(root),
        services=_parse_services(root),
        remarks=_parse_remarks(root),
        complements=_parse_complements(root),
    )


@router.get(
    '/{icao}',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[RotaerResponse],
    summary='Dados ROTAER de um aeródromo',
    description=(
        'Retorna dados detalhados do ROTAER via AISWEB. '
        'Use force="html" para obter o HTML bruto.'
    ),
)
async def get_rotaer(
    icao: str,
    force: Annotated[
        str | None,
        Query(description='Forçar formato de retorno (ex: "html")'),
    ] = None,
) -> ApiResponse[RotaerResponse]:
    params: dict[str, str] = {
        'area': 'rotaer',
        'icaoCode': icao.upper(),
    }
    if force:
        params['force'] = force

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

    if force and force.lower() == 'html':
        return success_response(
            data=RotaerResponse(rotaer_html=response.text)
        )

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail='Resposta inválida do AISWEB',
        )

    rotaer_data = _parse_rotaer_xml(root, icao)
    return success_response(data=RotaerResponse(data=rotaer_data))
