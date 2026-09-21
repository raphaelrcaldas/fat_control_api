"""Validação e manutenção das localidades especiais de referência global."""

from http import HTTPStatus

from fastapi import HTTPException
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fcontrol_api.models.shared.estados_cidades import (
    Cidade,
    GrupoLocEsp,
    LocEspIcao,
)
from fcontrol_api.schemas.cegep.gle import LocEspCreate, LocEspUpdate


async def carregar_localidades(
    session: AsyncSession, ids: set[int]
) -> dict[int, tuple[GrupoLocEsp, Cidade]]:
    linhas = (
        await session.execute(
            select(GrupoLocEsp, Cidade)
            .join(Cidade, Cidade.codigo == GrupoLocEsp.cidade_id)
            .where(GrupoLocEsp.id.in_(ids))
        )
    ).all()
    return {loc.id: (loc, cidade) for loc, cidade in linhas}


async def _assert_cidade_existe(session: AsyncSession, cidade_id: int) -> None:
    existe = await session.scalar(
        select(Cidade.codigo).where(Cidade.codigo == cidade_id)
    )
    if not existe:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail='Cidade não encontrada',
        )


async def _assert_cidade_livre(
    session: AsyncSession, cidade_id: int, excluir_id: int | None = None
) -> None:
    """Uma cidade e localidade especial uma unica vez (unique no banco).

    Checado aqui para devolver mensagem util em vez do IntegrityError.
    """
    stmt = select(GrupoLocEsp.id).where(GrupoLocEsp.cidade_id == cidade_id)
    if excluir_id is not None:
        stmt = stmt.where(GrupoLocEsp.id != excluir_id)
    if await session.scalar(stmt):
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail='Esta cidade já está cadastrada como localidade especial',
        )


async def _assert_icaos_livres(
    session: AsyncSession, icaos: list[str], excluir_id: int | None = None
) -> None:
    """Um aerodromo atende uma so localidade (unique no banco).

    Sem esta checagem, mover um ICAO de uma localidade para outra devolve
    IntegrityError 500 em vez de dizer onde ele ja esta.
    """
    if not icaos:
        return
    stmt = (
        select(LocEspIcao.icao, Cidade.nome, Cidade.uf)
        .join(GrupoLocEsp, GrupoLocEsp.id == LocEspIcao.loc_esp_id)
        .join(Cidade, Cidade.codigo == GrupoLocEsp.cidade_id)
        .where(LocEspIcao.icao.in_(icaos))
    )
    if excluir_id is not None:
        stmt = stmt.where(LocEspIcao.loc_esp_id != excluir_id)
    conflitos = (await session.execute(stmt)).all()
    if conflitos:
        ocupados = ', '.join(
            f'{icao} (em {nome} - {uf})' for icao, nome, uf in conflitos
        )
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=f'ICAO já vinculado a outra localidade: {ocupados}',
        )


async def criar_localidade(
    session: AsyncSession, data: LocEspCreate
) -> GrupoLocEsp:
    """Valida referências e cria a localidade com seus ICAOs."""
    await _assert_cidade_existe(session, data.cidade_id)
    await _assert_cidade_livre(session, data.cidade_id)
    await _assert_icaos_livres(session, data.icaos)

    loc = GrupoLocEsp(
        cidade_id=data.cidade_id,
        grupo=data.grupo,
        fuso=data.fuso,
    )
    session.add(loc)
    await session.flush()

    for icao in data.icaos:
        session.add(LocEspIcao(loc_esp_id=loc.id, icao=icao))

    await session.flush()
    await session.refresh(loc, ['cidade', 'icaos'])

    return loc


async def atualizar_localidade(
    session: AsyncSession, loc: GrupoLocEsp, data: LocEspUpdate
) -> None:
    """Atualiza o cadastro e sincroniza somente os ICAOs alterados."""
    await _assert_cidade_existe(session, data.cidade_id)
    await _assert_cidade_livre(session, data.cidade_id, excluir_id=loc.id)
    await _assert_icaos_livres(session, data.icaos, excluir_id=loc.id)

    loc.cidade_id = data.cidade_id
    loc.grupo = data.grupo
    loc.fuso = data.fuso

    atuais = {item.icao for item in loc.icaos}
    novos = set(data.icaos)
    if atuais != novos:
        removidos = atuais - novos
        if removidos:
            await session.execute(
                sa_delete(LocEspIcao).where(
                    LocEspIcao.loc_esp_id == loc.id,
                    LocEspIcao.icao.in_(removidos),
                )
            )
        for icao in sorted(novos - atuais):
            session.add(LocEspIcao(loc_esp_id=loc.id, icao=icao))
        await session.flush()

    await session.refresh(loc, ['cidade', 'icaos'])
