from datetime import date, datetime, time
from http import HTTPStatus

from fastapi import HTTPException
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.models.cegep.comiss import Comissionamento
from fcontrol_api.schemas.missoes import UserFragMis


async def verificar_usrs_comiss(
    users: list[UserFragMis],
    afast: datetime,
    regres: datetime,
    session: AsyncSession,
) -> None:
    """
    Recebe uma lista de usuários na missão e
    verifica se os mesmos estão comissionados e
    se a data da missão está contida na data do
    comissionamento
    """
    # procura comissionamentos abertos dos usuários envolvidos na missão
    query_comiss = select(Comissionamento).where(
        Comissionamento.user_id.in_([u.user_id for u in users])
    )
    result_comiss = (await session.scalars(query_comiss)).all()

    user_no_comiss: list[UserFragMis] = []
    user_no_mis: list[UserFragMis] = []
    for uf in users:
        # todos os comissionamentos abertos deste usuário
        comiss_for_user = [c for c in result_comiss if c.user_id == uf.user_id]

        # se não houver comissionamento aberto para o usuário
        if not comiss_for_user:
            user_no_comiss.append(uf)
            continue

        # verifica se a missão está contida no intervalo do comissionamento
        checar_periodo: list[bool] = []
        for c in comiss_for_user:
            comiss_data_ab = datetime.combine(c.data_ab, time(0, 0, 0))
            comiss_data_fc = datetime.combine(c.data_fc, time(23, 59, 59))
            checar_periodo.append(
                comiss_data_ab <= afast and regres <= comiss_data_fc
            )

        if not any(checar_periodo):
            user_no_mis.append(uf)

    if user_no_mis or user_no_comiss:
        msg_parts = []
        if user_no_comiss:
            msg = '\nOs seguintes militares não estão comissionados:'
            for uf in user_no_comiss:
                row = f'\n - {uf.user.p_g} {uf.user.nome_guerra}'.upper()
                msg += row
            msg_parts.append(msg)

        if user_no_mis:
            msg = (
                '\nOs seguintes militares não têm comissionamento '
                'cobrindo o período da missão:'
            )
            for uf in user_no_mis:
                msg += f'\n - {uf.user.p_g} {uf.user.nome_guerra}'.upper()
            msg_parts.append(msg)

        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='\n\n'.join(msg_parts),
        )


async def verificar_conflito_comiss(
    user_id: int,
    data_ab: date,
    data_fc: date,
    session: AsyncSession,
    comiss_id: int = None,
):
    query = select(Comissionamento).where(
        and_(
            (Comissionamento.user_id == user_id),
            (Comissionamento.data_ab <= data_fc),
            (data_ab <= Comissionamento.data_fc),
        )
    )

    if comiss_id:
        query = query.where(Comissionamento.id != comiss_id)

    comiss_conflict = await session.scalar(query)
    if comiss_conflict:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Comissionamento em conflito de datas para este usuário',
        )


# ============================================================
# Funções de cache para comissionamento
# ============================================================


async def recalcular_cache_comiss(
    comiss_id: int,
    session: AsyncSession,
) -> dict:
    """
    Recalcula o cache de um comissionamento específico.
    Retorna o dict com os valores calculados.
    """
    from fcontrol_api.models.cegep.missoes import (  # noqa: PLC0415
        FragMis,
        UserFrag,
    )
    from fcontrol_api.schemas.missoes import FragMisSchema  # noqa: PLC0415
    from fcontrol_api.utils.financeiro import (  # noqa: PLC0415
        custo_missao,
        verificar_modulo,
    )

    # Buscar comissionamento
    comiss = await session.scalar(
        select(Comissionamento).where(Comissionamento.id == comiss_id)
    )

    if not comiss:
        return {}

    # Buscar missões do comissionamento
    query = (
        select(FragMis, UserFrag)
        .join(
            UserFrag,
            and_(
                UserFrag.user_id == comiss.user_id,
                UserFrag.sit == 'c',
                UserFrag.frag_id == FragMis.id,
            ),
        )
        .where(
            and_(
                FragMis.afast >= comiss.data_ab,
                FragMis.regres <= comiss.data_fc,
            )
        )
        .order_by(FragMis.afast)
    )

    result = await session.execute(query)
    registros: list[tuple[FragMis, UserFrag]] = result.all()

    # Inicializar acumuladores
    dias_comp = 0
    diarias_comp = 0
    vals_comp = 0
    missoes_data = []

    for missao, user_frag in registros:
        # Serializar missão
        missao_data = FragMisSchema.model_validate(missao).model_dump(
            exclude={'users'}
        )

        # Calcular custos usando JSONB da missão
        missao_data = custo_missao(
            user_frag.p_g,
            user_frag.sit,
            missao_data,
        )

        # Acumular valores
        diarias_comp += missao_data['diarias']
        dias_comp += missao_data['dias']
        vals_comp += missao_data['valor_total']
        missoes_data.append(missao_data)

    # Calcular módulo
    modulo = verificar_modulo(missoes_data) if missoes_data else False

    # Calcular completude
    if comiss.dias_cumprir:
        completude = (
            dias_comp / comiss.dias_cumprir if comiss.dias_cumprir else 0
        )
    else:
        soma_cumprir = comiss.valor_aj_ab + comiss.valor_aj_fc
        completude = vals_comp / soma_cumprir if soma_cumprir else 0

    completude = min(completude, 1)
    completude = round(completude * 100, 1)  # Retorna já em percentual (0-100)

    # Montar cache
    cache_data = {
        'dias_comp': dias_comp,
        'diarias_comp': diarias_comp,
        'vals_comp': vals_comp,
        'modulo': modulo,
        'completude': completude,
        'missoes_count': len(missoes_data),
        'updated_at': datetime.now().isoformat(),
    }

    # Atualizar no banco
    comiss.cache_calc = cache_data
    await session.flush()

    return cache_data


async def localizar_comiss_por_missao(
    user_id: int,
    data_afast: date,
    data_regres: date,
    session: AsyncSession,
) -> list[int]:
    """
    Localiza IDs de comissionamentos afetados por uma missão.
    """
    query = select(Comissionamento.id).where(
        and_(
            Comissionamento.user_id == user_id,
            Comissionamento.data_ab <= data_afast,
            Comissionamento.data_fc >= data_regres,
        )
    )

    result = await session.execute(query)
    return [id for (id,) in result.all()]


async def recalcular_comiss_afetados(
    user_id: int,
    data_afast: date,
    data_regres: date,
    session: AsyncSession,
) -> int:
    """
    Recalcula todos os comissionamentos afetados por uma missão.
    Retorna a quantidade de comissionamentos recalculados.
    """
    comiss_ids = await localizar_comiss_por_missao(
        user_id, data_afast, data_regres, session
    )

    for comiss_id in comiss_ids:
        await recalcular_cache_comiss(comiss_id, session)

    return len(comiss_ids)
