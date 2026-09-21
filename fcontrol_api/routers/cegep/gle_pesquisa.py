"""Pesquisa GLE em etapas da organização ativa, com permissão de etapas."""

from datetime import date
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from fcontrol_api.database import get_session
from fcontrol_api.models.estatistica.etapa import Etapa, Missao, OIEtapa
from fcontrol_api.models.shared.estados_cidades import LocEspIcao
from fcontrol_api.schemas.cegep.gle_pesquisa import PesquisaLocEspOut
from fcontrol_api.schemas.response import ApiResponse
from fcontrol_api.security import ActiveOrg, permission_checker
from fcontrol_api.services.gle.pesquisa import montar_pesquisa
from fcontrol_api.utils.responses import success_response

Session = Annotated[AsyncSession, Depends(get_session)]
router = APIRouter(prefix='/gle', tags=['CEGEP'])
ViewEtapa = Depends(permission_checker('estatistica.etapas', 'view'))


@router.get(
    '/pesquisa',
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[PesquisaLocEspOut],
    dependencies=[ViewEtapa],
)
async def pesquisar_missoes(
    session: Session,
    active_org: ActiveOrg,
    data_ini: Annotated[date | None, Query()] = None,
    data_fim: Annotated[date | None, Query()] = None,
    grupo: Annotated[int | None, Query(ge=1, le=2)] = None,
    loc_esp_id: Annotated[int | None, Query()] = None,
) -> ApiResponse[PesquisaLocEspOut]:
    """Missões que passaram por localidade especial.

    A pergunta é **binária**: a missão passou por lá ou não. Por isso o
    resultado agrupa por missão e as etapas descem só como evidência —
    não é relatório de horas nem de permanência.

    **Tocar em qualquer ponta conta**: origem e destino contam igual,
    porque ambos provam a passagem. Uma etapa que liga duas localidades
    especiais aparece uma vez, com os dois ICAOs em `icaos_loc_esp`.

    Só entram etapas com **esforço aéreo cadastrado** (ao menos uma
    `OIEtapa`): sem ele o lançamento está incompleto e não sustenta a
    passagem.

    Precisa vir declarada antes de `/{id}`, senão o path casa com a rota
    de detalhe e `pesquisa` reprova em 422.

    Sem paginação: a janela de datas é o que limita o volume, como em
    `estatistica/etapas`.
    """
    # `etapas` vive no schema `estatistica` e a ponte em `public` — o JOIN
    # cruza schemas, e o SQLAlchemy resolve pelos models.
    origem_loc = aliased(LocEspIcao, name='origem_loc')
    destino_loc = aliased(LocEspIcao, name='destino_loc')

    # Esforço aéreo vem por OIEtapa (`esf_aer_id` obrigatório lá): etapa sem
    # nenhuma OI é lançamento incompleto e não entra. EXISTS em vez de JOIN
    # porque a etapa pode ter várias OIs e o JOIN a duplicaria.
    tem_esf_aer = (
        select(OIEtapa.id).where(OIEtapa.etapa_id == Etapa.id).exists()
    )

    stmt = (
        select(Etapa, Missao, origem_loc, destino_loc)
        .join(Missao, Missao.id == Etapa.missao_id)
        .outerjoin(origem_loc, origem_loc.icao == Etapa.origem)
        .outerjoin(destino_loc, destino_loc.icao == Etapa.destino)
        .where(
            Missao.uae == active_org,
            # Simulador não sai do chão: não passa por localidade nenhuma.
            Missao.is_simulador.is_(False),
            (origem_loc.id.is_not(None)) | (destino_loc.id.is_not(None)),
            tem_esf_aer,
        )
        .order_by(Etapa.data, Etapa.dep, Etapa.id)
    )

    if data_ini:
        stmt = stmt.where(Etapa.data >= data_ini)
    if data_fim:
        stmt = stmt.where(Etapa.data <= data_fim)

    linhas = (await session.execute(stmt)).all()
    return success_response(
        data=await montar_pesquisa(session, linhas, grupo, loc_esp_id)
    )
