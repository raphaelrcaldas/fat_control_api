"""Servicos para Ordem de Missao (OM)."""

from collections.abc import Sequence
from datetime import datetime
from http import HTTPStatus
from typing import Protocol

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from fcontrol_api.models.shared.om import OrdemTripulacao
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
    session: AsyncSession, ordem_id: int, tripulacao_data
) -> list[OrdemTripulacao]:
    """
    Cria registros de tripulacao usando batch query para evitar N+1.

    Args:
        session: Sessao do banco de dados
        ordem_id: ID da ordem de missao
        tripulacao_data: Dados da tripulacao (TripulacaoOM schema)

    Returns:
        As linhas criadas, com `.tripulante` (e `.tripulante.user`, via
        lazy='selectin') ja em memoria — o snapshot de auditoria le o
        nome de guerra sem disparar lazy-load fora do greenlet.
    """
    # Coletar todos os IDs de tripulantes
    all_trip_ids = []
    tripulacao_dict = tripulacao_data.model_dump()
    for trip_ids in tripulacao_dict.values():
        all_trip_ids.extend(trip_ids)

    if not all_trip_ids:
        return []

    # Uma unica query para buscar todos os tripulantes
    tripulantes_result = await session.scalars(
        select(Tripulante)
        .where(Tripulante.id.in_(all_trip_ids))
        .options(selectinload(Tripulante.user))
    )
    tripulantes_map = {t.id: t for t in tripulantes_result.all()}

    # Criar registros de tripulacao usando o map
    criadas: list[OrdemTripulacao] = []
    for funcao, trip_ids in tripulacao_dict.items():
        for trip_id in trip_ids:
            tripulante = tripulantes_map.get(trip_id)
            if not tripulante or not tripulante.user:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=f'Tripulante {trip_id} não encontrado',
                )
            trip_ordem = OrdemTripulacao(
                ordem_id=ordem_id,
                tripulante_id=trip_id,
                funcao=funcao,
                p_g=tripulante.user.p_g,  # Snapshot do p_g atual
            )
            # `tripulante` nao e anotado no model (logo nao e campo do
            # dataclass): a atribuicao pos-construcao popula a relacao com
            # o objeto ja carregado aqui, evitando lazy-load no snapshot.
            trip_ordem.tripulante = tripulante
            session.add(trip_ordem)
            criadas.append(trip_ordem)

    return criadas
