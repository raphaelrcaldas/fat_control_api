"""Servicos para Ordem de Missao (OM)."""

from collections.abc import Sequence
from datetime import datetime
from http import HTTPStatus
from typing import Protocol

from fastapi import HTTPException
from sqlalchemy import Integer, cast, extract, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from fcontrol_api.models.shared.funcoes import FuncaoUae
from fcontrol_api.models.shared.om import (
    OrdemEtapa,
    OrdemMissao,
    OrdemTripulacao,
)
from fcontrol_api.models.shared.tripulantes import Tripulante


class EtapaLike(Protocol):
    """Campos mínimos de uma etapa para a validação de integridade.

    Satisfeito tanto pelo schema de entrada (EtapaCreate) quanto pelo
    model persistido (OrdemEtapa).
    """

    dt_dep: datetime
    dt_arr: datetime
    origem: str
    dest: str


def validar_integridade_etapas(
    etapas: Sequence[EtapaLike],
    esf_aer: int,
    *,
    exigir_continuidade: bool,
) -> None:
    """
    Valida regras de negócio entre etapas e o esforço aéreo da OM.

    Espelha as regras do frontend (ordemValidation.ts) para que a
    integridade não dependa do cliente:
    - decolagens duplicadas (mesma dt_dep);
    - sobreposição de horários entre etapas;
    - continuidade da rota (origem == destino da etapa anterior),
      exigida apenas quando a ordem resulta aprovada;
    - esf_aer da OM >= soma do tempo de voo das etapas.

    Levanta HTTPException 400 com todos os erros encontrados.
    """
    erros: list[str] = []
    ordenadas = sorted(etapas, key=lambda e: e.dt_dep)

    # Decolagens duplicadas (mesma dt_dep)
    decolagens: dict[datetime, list[int]] = {}
    for idx, etapa in enumerate(ordenadas, start=1):
        decolagens.setdefault(etapa.dt_dep, []).append(idx)
    for indices in decolagens.values():
        if len(indices) > 1:
            lista = ', '.join(str(i) for i in indices)
            erros.append(
                f'Períodos duplicados: as etapas {lista} possuem a '
                f'mesma data/hora de decolagem'
            )

    # Sobreposição de horários entre pares de etapas
    for i in range(len(ordenadas)):
        for j in range(i + 1, len(ordenadas)):
            e1, e2 = ordenadas[i], ordenadas[j]
            if e1.dt_dep < e2.dt_arr and e1.dt_arr > e2.dt_dep:
                erros.append(
                    f'Sobreposição de horários: a etapa {i + 1} '
                    f'sobrepõe a etapa {j + 1}'
                )

    # Continuidade da rota (exigida na aprovação)
    if exigir_continuidade:
        for i in range(1, len(ordenadas)):
            anterior, atual = ordenadas[i - 1], ordenadas[i]
            if atual.origem != anterior.dest:
                erros.append(
                    f'Etapa {i + 1}: a origem deve ser igual ao destino '
                    f'da etapa anterior ({anterior.dest})'
                )

    # esf_aer da OM >= soma do tempo de voo das etapas
    soma = sum(
        int((e.dt_arr - e.dt_dep).total_seconds() / 60) for e in ordenadas
    )
    if soma > 0 and esf_aer < soma:
        erros.append(
            f'Esforço aéreo da OM ({esf_aer} min) deve ser maior ou '
            f'igual à soma do tempo de voo das etapas ({soma} min)'
        )

    if erros:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='; '.join(erros),
        )


async def criar_tripulacao_batch(
    session: AsyncSession,
    ordem_id: int,
    tripulacao_data,
    *,
    uae: str,
    p_g_preservado: dict[tuple[int, str], str] | None = None,
) -> list[OrdemTripulacao]:
    """
    Cria registros de tripulacao usando batch query para evitar N+1.

    Args:
        session: Sessao do banco de dados
        ordem_id: ID da ordem de missao
        tripulacao_data: Dados da tripulacao (TripulacaoOM schema)
        uae: Org ativa da requisicao. Escopa tanto o tripulante quanto a
            funcao: o gate de permissao autoriza a ACAO, nao o ALVO, e o
            id do tripulante vem do corpo da requisicao. Sem este filtro,
            um id de outra unidade entra na OM e o GET seguinte devolve
            nome, id_fab e posto daquele militar.
        p_g_preservado: Mapa (tripulante_id, funcao) -> p_g ja gravado.
            O update da OM apaga e recria a tripulacao; sem este mapa,
            editar em 2026 uma OM de 2024 recarimbaria o posto ATUAL de
            todo mundo, destruindo o snapshot historico. Quem estava na
            ordem mantem o p_g de origem; quem entra agora recebe o
            posto atual do militar. Na criacao (POST) fica None, e todos
            recebem o posto atual.

    Returns:
        As linhas criadas, com `.tripulante` (e `.tripulante.user`, via
        lazy='selectin') ja em memoria — o snapshot de auditoria le o
        nome de guerra sem disparar lazy-load fora do greenlet.
    """
    # Coletar todos os IDs de tripulantes
    all_trip_ids = []
    tripulacao_dict = tripulacao_data.root
    for trip_ids in tripulacao_dict.values():
        all_trip_ids.extend(trip_ids)

    if not all_trip_ids:
        return []

    # A lista de funcoes e dado, nao codigo: valida-se contra o que a
    # unidade opera. Antes, chaves fora de um conjunto fixo (`md`, `ml`)
    # eram descartadas em silencio pelo schema — e como o update apaga e
    # recria a tripulacao, uma edicao inocua apagava esses tripulantes.
    funcoes_uae = set(
        await session.scalars(
            select(FuncaoUae.func_cod).where(FuncaoUae.uae == uae)
        )
    )
    invalidas = sorted(set(tripulacao_dict) - funcoes_uae)
    if invalidas:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=(
                f'Função não operada por esta unidade: {", ".join(invalidas)}'
            ),
        )

    # Uma unica query para buscar todos os tripulantes, escopada na org
    # ativa (o id vem do corpo da requisicao, ver `uae` no docstring).
    tripulantes_result = await session.scalars(
        select(Tripulante)
        .where(Tripulante.id.in_(all_trip_ids), Tripulante.uae == uae)
        .options(selectinload(Tripulante.user))
    )
    tripulantes_map = {t.id: t for t in tripulantes_result.all()}

    # Criar registros de tripulacao usando o map
    preservado = p_g_preservado or {}
    criadas: list[OrdemTripulacao] = []
    for funcao, trip_ids in tripulacao_dict.items():
        for trip_id in trip_ids:
            tripulante = tripulantes_map.get(trip_id)
            if not tripulante or not tripulante.user:
                # Mensagem neutra de proposito: nao revela se o id existe
                # em outra unidade.
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=f'Tripulante {trip_id} não encontrado',
                )
            # Preserva o snapshot de quem ja estava na ordem nesta
            # funcao; so tripulante novo recebe o posto atual.
            p_g = preservado.get((trip_id, funcao), tripulante.user.p_g)
            trip_ordem = OrdemTripulacao(
                ordem_id=ordem_id,
                tripulante_id=trip_id,
                funcao=funcao,
                p_g=p_g,
            )
            # `tripulante` nao e anotado no model (logo nao e campo do
            # dataclass): a atribuicao pos-construcao popula a relacao com
            # o objeto ja carregado aqui, evitando lazy-load no snapshot.
            trip_ordem.tripulante = tripulante
            session.add(trip_ordem)
            criadas.append(trip_ordem)

    return criadas


def montar_etapa(ordem_id: int, dados: EtapaLike) -> OrdemEtapa:
    """Monta uma OrdemEtapa a partir do payload de entrada.

    `tvoo_etp` nao vem do cliente: e derivado de dt_arr - dt_dep em
    minutos. Criacao e atualizacao da OM montam a etapa do mesmo jeito,
    entao a derivacao mora aqui e nao em cada handler.
    """
    tvoo_etp = int((dados.dt_arr - dados.dt_dep).total_seconds() / 60)
    return OrdemEtapa(
        ordem_id=ordem_id,
        dt_dep=dados.dt_dep,
        origem=dados.origem,
        dest=dados.dest,
        dt_arr=dados.dt_arr,
        alternativa=dados.alternativa,
        tvoo_etp=tvoo_etp,
        tvoo_alt=dados.tvoo_alt,
        qtd_comb=dados.qtd_comb,
        esf_aer=dados.esf_aer,
    )


async def assert_numero_om_livre(
    session: AsyncSession,
    *,
    numero: str,
    uae: str,
    ano: int,
    excluir_id: int,
    rotulo: str | None = None,
) -> None:
    """Garante que o numero nao esta em uso na mesma UAE e ano.

    `excluir_id` tira a propria ordem da busca. `rotulo` entra na
    mensagem quando o numero foi digitado pelo usuario; omitido, a
    mensagem fala de "este numero" (numero recem-emitido).
    """
    existing = await session.scalar(
        select(OrdemMissao).where(
            OrdemMissao.numero == numero,
            OrdemMissao.id != excluir_id,
            OrdemMissao.deleted_at.is_(None),
            extract('year', OrdemMissao.data_saida) == ano,
            OrdemMissao.uae == uae,
        )
    )
    if existing:
        alvo = f'o número {rotulo}' if rotulo else 'este número'
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=(
                f'Já existe uma ordem com {alvo} no ano {ano} para a UAE {uae}'
            ),
        )


async def emitir_numero_om(
    session: AsyncSession, *, uae: str, ano: int, excluir_id: int
) -> str:
    """Emite o proximo numero sequencial da OM na UAE e ano.

    Usa MAX(numero)+1 (e nao COUNT+1) para que a numeracao seja
    permanente: um numero emitido nunca e reusado, mesmo que a OM seja
    cancelada. O filtro regex '^[0-9]+$' descarta 'auto' (rascunhos) e
    numeros editados a mao que nao sejam numericos, e deleted_at IS NULL
    ignora OMs excluidas.

    O advisory lock transacional serializa a emissao por (UAE, ano): sem
    ele, duas aprovacoes simultaneas leriam o mesmo MAX e emitiriam
    numeros duplicados. E liberado no commit.
    """
    await session.execute(
        select(
            func.pg_advisory_xact_lock(
                func.hashtextextended(f'om_numero:{uae}:{ano}', 0)
            )
        )
    )

    max_seq = await session.scalar(
        select(func.max(cast(OrdemMissao.numero, Integer))).where(
            OrdemMissao.numero.op('~')('^[0-9]+$'),
            OrdemMissao.deleted_at.is_(None),
            extract('year', OrdemMissao.data_saida) == ano,
            OrdemMissao.uae == uae,
        )
    )

    numero = f'{(max_seq or 0) + 1:03d}'

    # Pos-condicao defensiva: sob o lock, MAX+1 ja e unico por
    # construcao. A checagem cobre o caso de um numero manual ter
    # ocupado a faixa por outro caminho.
    await assert_numero_om_livre(
        session, numero=numero, uae=uae, ano=ano, excluir_id=excluir_id
    )
    return numero
