"""Validação de sobreposição de faixas de vigência (soldo/diária).

Cada faixa é o intervalo inclusivo ``[data_inicio, data_fim]``; ``data_fim``
nulo representa vigência em aberto (até +infinito). Duas faixas com a mesma
chave (mesmo ``pg``; ou mesmo ``grupo_pg`` + ``grupo_cid``) não podem se
sobrepor — caso contrário o valor pago por dia se torna não-determinístico,
pois ``_buscar_valor_por_dia`` usa a primeira faixa que casa a data.

Esta é a guarda da camada de aplicação (retorna HTTP 409 antes de gravar). O
banco mantém ainda uma constraint EXCLUDE (btree_gist) como rede de segurança.
"""

from datetime import date
from http import HTTPStatus

from fastapi import HTTPException
from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


async def garantir_sem_sobreposicao(
    session: AsyncSession,
    model: type,
    filtros_chave: list[ColumnElement[bool]],
    data_inicio: date,
    data_fim: date | None,
    excluir_id: int | None = None,
) -> None:
    """Levanta HTTP 409 se ``[data_inicio, data_fim]`` sobrepor outra faixa.

    ``filtros_chave`` são as condições de igualdade da chave da faixa
    (ex.: ``[Soldo.pg == 'cb']`` ou ``[DiariaValor.grupo_pg == 3,
    DiariaValor.grupo_cid == 1]``). ``excluir_id`` ignora a própria linha
    em atualizações.
    """
    # Intervalos inclusivos [a, b] e [c, d] se sobrepõem sse a <= d e c <= b,
    # tratando data_fim nulo (de qualquer lado) como +infinito.
    condicoes = [
        *filtros_chave,
        # faixa existente termina em/depois do início do candidato
        or_(model.data_fim.is_(None), model.data_fim >= data_inicio),
    ]
    if data_fim is not None:
        # faixa existente começa em/antes do fim do candidato
        condicoes.append(model.data_inicio <= data_fim)

    query = select(model.id).where(*condicoes)
    if excluir_id is not None:
        query = query.where(model.id != excluir_id)

    conflito = await session.scalar(query.limit(1))
    if conflito is not None:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail=(
                'Conflito de vigência: o período informado se sobrepõe a '
                'uma faixa já cadastrada para esta chave'
            ),
        )
