"""Alteração do conteúdo da missão, sem encerrar a transação do chamador."""

from collections.abc import Sequence
from http import HTTPStatus

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.models.cegep.gle import MilitarGle, MissaoGle, TrechoGle
from fcontrol_api.models.shared.users import User
from fcontrol_api.schemas.cegep.gle_missao import (
    MissaoGleCreate,
    MissaoGleUpdate,
)
from fcontrol_api.services.gle.localidades import carregar_localidades


async def aplicar_conteudo(
    session: AsyncSession,
    missao: MissaoGle,
    payload: MissaoGleCreate | MissaoGleUpdate,
    users: Sequence[User],
) -> None:
    """Substitui trechos e militares da missão pelos informados.

    O chamador carrega users com o filtro da organização ativa. IDs do
    payload ausentes nessa seleção são recusados sem revelar outra org.
    """
    ids_locs = {t.loc_esp_id for t in payload.trechos}
    por_id = await carregar_localidades(session, ids_locs)
    faltantes = sorted(ids_locs - por_id.keys())
    if faltantes:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail=(
                'Localidade especial não encontrada: '
                + ', '.join(str(i) for i in faltantes)
            ),
        )

    achados = {u.id for u in users}
    ausentes = sorted(set(payload.militares_ids) - achados)
    if ausentes:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail=(
                'Militar não encontrado: '
                + ', '.join(str(i) for i in ausentes)
            ),
        )
    # Posto atual de quem entra agora; quem já estava preserva o snapshot.
    ja_gravados = {m.user_id: m.p_g for m in missao.militares}

    # Esvazia e dá `flush` ANTES de reinserir: na mesma descarga, o
    # SQLAlchemy emite o INSERT das novas linhas antes do DELETE das
    # antigas e `uq_militar_gle_missao_user` estoura quando o mesmo militar
    # permanece na missão.
    missao.trechos.clear()
    missao.militares.clear()
    await session.flush()

    missao.trechos = [
        TrechoGle(
            loc_esp_id=t.loc_esp_id,
            chegada=t.chegada,
            afastamento=t.afastamento,
        )
        for t in payload.trechos
    ]
    missao.militares = [
        MilitarGle(
            user_id=u.id,
            p_g=ja_gravados.get(u.id, u.p_g),
        )
        for u in users
    ]
