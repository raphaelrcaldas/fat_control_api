"""Projeções de GLE para os contratos de resposta da API."""

from collections.abc import Sequence
from datetime import date
from http import HTTPStatus

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.models.cegep.gle import MissaoGle
from fcontrol_api.models.shared.estados_cidades import GrupoLocEsp
from fcontrol_api.schemas.cegep.gle import LocEspOut
from fcontrol_api.schemas.cegep.gle_missao import (
    MilitarMissaoOut,
    MissaoGleOut,
    MissaoGleResumo,
)
from fcontrol_api.services.gle.apuracao import (
    ROTULO_PERCENTUAL,
    MilitarApurar,
    TrechoApurar,
    apurar,
)
from fcontrol_api.services.gle.localidades import carregar_localidades


def montar_localidade(loc: GrupoLocEsp) -> LocEspOut:
    return LocEspOut(
        id=loc.id,
        cidade_id=loc.cidade_id,
        grupo=loc.grupo,
        fuso=loc.fuso,
        cidade=loc.cidade,
        icaos=sorted(item.icao for item in loc.icaos),
    )


async def montar_missao(
    session: AsyncSession, missao: MissaoGle
) -> MissaoGleOut:
    """Recalcula a missão salva e devolve a apuração completa."""
    ids_locs = {t.loc_esp_id for t in missao.trechos}
    por_id = await carregar_localidades(session, ids_locs)

    # Localidade apagada depois de a missão ser salva: o FK é RESTRICT, mas
    # a defesa fica porque o `montar_missao` também serve a dado antigo.
    faltantes = sorted(ids_locs - por_id.keys())
    if faltantes:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail=(
                'Localidade especial da missão não existe mais: '
                + ', '.join(str(i) for i in faltantes)
            ),
        )

    # `p_g` gravado, não o atual: promover alguém não reescreve a apuração.
    militares = sorted(
        missao.militares,
        key=lambda m: (
            m.user.posto.ant,
            m.user.ult_promo or date.min,
            m.user.ant_rel or 0,
        ),
    )
    apuracao = await apurar(
        session,
        [
            TrechoApurar(t.loc_esp_id, t.chegada, t.afastamento)
            for t in missao.trechos
        ],
        [
            MilitarApurar(
                m.user_id,
                m.p_g,
                m.user.nome_guerra,
                m.user.nome_completo,
                m.user.saram,
            )
            for m in militares
        ],
        por_id,
    )
    por_user = {uid: (soldo, valor) for uid, soldo, valor in apuracao.valores}

    return MissaoGleOut(
        id=missao.id,
        descricao=missao.descricao,
        obs=missao.obs,
        created_at=missao.created_at,
        multiplicador=apuracao.multiplicador,
        percentual=apuracao.percentual,
        trechos=apuracao.trechos,
        militares=[
            MilitarMissaoOut(
                user_id=m.user_id,
                p_g=m.p_g,
                nome_guerra=m.user.nome_guerra,
                nome_completo=m.user.nome_completo,
                saram=m.user.saram,
                soldo=por_user[m.user_id][0],
                valor=por_user[m.user_id][1],
            )
            for m in militares
        ],
    )


async def resumir_missoes(
    session: AsyncSession, missoes: Sequence[MissaoGle]
) -> list[MissaoGleResumo]:
    """Carrega localidades em lote e resume os períodos e participantes."""
    ids_locs = {t.loc_esp_id for m in missoes for t in m.trechos}
    por_id = await carregar_localidades(session, ids_locs)

    resumos: list[MissaoGleResumo] = []
    for missao in missoes:
        datas = [t.chegada for t in missao.trechos]
        fins = [t.afastamento for t in missao.trechos]
        grupos = {
            por_id[t.loc_esp_id][0].grupo
            for t in missao.trechos
            if t.loc_esp_id in por_id
        }
        # Nomes sem repetir e em ordem: a lista serve para reconhecer a
        # missão de relance, não para detalhar.
        cidades = sorted({
            f'{por_id[t.loc_esp_id][1].nome} - {por_id[t.loc_esp_id][1].uf}'
            for t in missao.trechos
            if t.loc_esp_id in por_id
        })
        resumos.append(
            MissaoGleResumo(
                id=missao.id,
                descricao=missao.descricao,
                created_at=missao.created_at,
                total_trechos=len(missao.trechos),
                total_militares=len(missao.militares),
                percentual=' e '.join(
                    ROTULO_PERCENTUAL[g] for g in sorted(grupos)
                ),
                primeira_data=min(datas),
                ultima_data=max(fins),
                localidades=cidades,
            )
        )

    return resumos
