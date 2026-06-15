from datetime import date, datetime, time, timedelta
from http import HTTPStatus

from fastapi import HTTPException
from sqlalchemy import and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.models.cegep.comiss import Comissionamento
from fcontrol_api.models.cegep.missoes import FragMis, UserFrag
from fcontrol_api.schemas.cegep.missoes import FragMisSchema, UserFragMis
from fcontrol_api.services.custos import custo_missao
from fcontrol_api.utils.datas import listar_datas_entre


async def verificar_usrs_comiss(
    users: list[UserFragMis],
    afast: datetime,
    regres: datetime,
    session: AsyncSession,
    active_org: str,
) -> None:
    """
    Recebe uma lista de usuários na missão e
    verifica se os mesmos estão comissionados e
    se a data da missão está contida na data do
    comissionamento
    """
    # procura comissionamentos da org ativa dos usuários da missão
    # (missão da org A só conta para comissionamento da org A)
    query_comiss = select(Comissionamento).where(
        Comissionamento.user_id.in_([u.user_id for u in users]),
        Comissionamento.uae == active_org,
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
    uae: str,
    comiss_id: int | None = None,
):
    # Escopo multi-tenant: conflito de datas é avaliado apenas dentro da
    # org ativa. Usuários são diretório universal, mas comissionamentos são
    # por unidade — um aberto em outra org não deve bloquear esta.
    query = select(Comissionamento).where(
        and_(
            (Comissionamento.user_id == user_id),
            (Comissionamento.uae == uae),
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


def filtro_missoes_periodo(uae, data_ab, data_fc):
    """Filtro canônico das missões que pertencem ao período de um
    comissionamento.

    Compara em granularidade de DATA (`afast.date()`/`regres.date()`), com
    `data_ab` e `data_fc` **inclusivos** — a mesma fronteira usada por
    `verificar_usrs_comiss` (gate ao salvar a missão) e por
    `localizar_comiss_por_missao` (gatilho de recálculo). As queries de
    agregação/leitura usavam `FragMis.regres <= data_fc`, que coage o
    `date` para 00:00 e excluía missões que regressam no próprio
    `data_fc` — divergindo dos demais pontos e fazendo a missão sumir do
    cache mesmo tendo sido validada para dentro do comissionamento.
    Centralizar a fronteira aqui evita que esses pontos voltem a divergir.

    `uae`/`data_ab`/`data_fc` aceitam valores Python ou colunas SQL (ex.:
    `Comissionamento.data_fc`), servindo tanto ao recálculo quanto aos
    joins correlacionados do update.
    """
    return and_(
        FragMis.uae == uae,
        func.date(FragMis.afast) >= data_ab,
        func.date(FragMis.regres) <= data_fc,
    )


def verificar_modulo(missoes: list[dict]) -> bool:
    """Recebe uma lista de missões e verifica
    se houve um afastamento maior que 15 dias
    em alguma delas.
    """
    DIAS_MODULO = 16

    datas: list[date] = []
    for m in missoes:
        datas_missao = listar_datas_entre(
            m['afast'].date(), m['regres'].date()
        )
        datas.extend(datas_missao)
    datas.sort()

    dias_consec = 1
    for i, _ in enumerate(datas):
        anterior = datas[i - 1]
        atual = datas[i]

        dif = (atual - anterior).days

        if dif != 1:
            dias_consec = 1
            continue

        dias_consec += 1

        if dias_consec >= DIAS_MODULO:
            return True

    return False


async def recalcular_cache_comiss(
    comiss_id: int,
    session: AsyncSession,
) -> dict:
    """
    Recalcula o cache de um comissionamento específico.
    Retorna o dict com os valores calculados.
    """
    # Buscar comissionamento
    comiss = await session.scalar(
        select(Comissionamento).where(Comissionamento.id == comiss_id)
    )

    # Buscar missões do comissionamento (mesma org do comissionamento)
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
            filtro_missoes_periodo(
                comiss.uae, comiss.data_ab, comiss.data_fc
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
        'vals_comp': round(vals_comp, 2),
        'modulo': modulo,
        'completude': completude,
        'missoes_count': len(missoes_data),
        'updated_at': datetime.now().isoformat(),
    }

    # Atualizar no banco
    comiss.cache_calc = cache_data
    await session.flush()

    return cache_data


async def validar_fechamento_comiss(
    comiss: Comissionamento,
    session: AsyncSession,
) -> None:
    """
    Valida as regras de fechamento de um comissionamento. Deve ser chamada
    sempre que o status passar a 'fechado'. Recalcula o cache (garantindo
    valores frescos) e levanta HTTPException 400 com todos os motivos
    acumulados se alguma regra não for satisfeita.

    Regras:
    - deve haver ao menos uma missão vinculada;
    - completude deve estar em 100%;
    - data_fc deve ser o dia seguinte à última missão (maior regres).
    """
    cache = await recalcular_cache_comiss(comiss.id, session)

    if cache['missoes_count'] == 0:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=(
                'Não há missões vinculadas para fechar o comissionamento.'
            ),
        )

    errors: list[str] = []

    if cache['completude'] < 100:
        errors.append(
            f'- Completude está em {cache["completude"]}%; '
            'o fechamento exige 100%'
        )

    # Última missão = maior regresso entre as vinculadas (sit='c', no
    # período). data_fc deve ser o dia seguinte.
    ultima_regres = await session.scalar(
        select(func.max(FragMis.regres))
        .join(
            UserFrag,
            and_(
                UserFrag.frag_id == FragMis.id,
                UserFrag.user_id == comiss.user_id,
                UserFrag.sit == 'c',
            ),
        )
        .where(
            filtro_missoes_periodo(
                comiss.uae, comiss.data_ab, comiss.data_fc
            )
        )
    )
    esperada = ultima_regres.date() + timedelta(days=1)
    if comiss.data_fc != esperada:
        errors.append(
            f'- Data de fechamento deve ser {esperada.strftime("%d/%m/%Y")} '
            '(dia seguinte à última missão)'
        )

    if errors:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='\n'.join(errors),
        )


async def localizar_comiss_por_missao(
    user_id: int,
    data_afast: date,
    data_regres: date,
    session: AsyncSession,
    uae: str,
) -> list[int]:
    """
    Localiza IDs de comissionamentos afetados por uma missão.

    Escopado por `uae`: missão de uma org só afeta comissionamentos
    da mesma org.
    """
    query = select(Comissionamento.id).where(
        and_(
            Comissionamento.user_id == user_id,
            Comissionamento.uae == uae,
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
    uae: str,
) -> int:
    """
    Recalcula todos os comissionamentos afetados por uma missão.
    Retorna a quantidade de comissionamentos recalculados.
    """
    comiss_ids = await localizar_comiss_por_missao(
        user_id, data_afast, data_regres, session, uae
    )

    for comiss_id in comiss_ids:
        await recalcular_cache_comiss(comiss_id, session)

    return len(comiss_ids)
