"""
Testes para validacoes dos schemas de etapa.

Testa a validacao de posicoes de piloto duplicadas (1P, 2P, IN, AL)
nos schemas EtapaCreate, EtapaCreateNested, EtapaUpdateNested e EtapaUpdate.
"""

from datetime import date, time

import pytest
from pydantic import ValidationError

from fcontrol_api.schemas.estatistica.etapa import (
    EtapaCreate,
    EtapaCreateNested,
    EtapaUpdate,
    EtapaUpdateNested,
    TripEtapaIn,
)

_BASE_ETAPA = dict(
    data=date(2025, 1, 1),
    origem='SBSP',
    destino='SBBR',
    dep=time(10, 0),
    arr=time(11, 30),
    tvoo=90,
    anv='KC30',
    pousos=1,
    sagem=False,
    parte1=True,
    obs=None,
)


def _trip(func_bordo: str, trip_id: int = 1) -> TripEtapaIn:
    return TripEtapaIn(trip_id=trip_id, func='pil', func_bordo=func_bordo)


# ---------------------------------------------------------------------------
# EtapaCreate
# ---------------------------------------------------------------------------


def test_etapa_create_sem_pilotos_aceita():
    EtapaCreate(missao_id=1, tripulantes=[], **_BASE_ETAPA)


def test_etapa_create_pilotos_distintos_aceita():
    trips = [_trip('1P', 1), _trip('2P', 2)]
    EtapaCreate(missao_id=1, tripulantes=trips, **_BASE_ETAPA)


def test_etapa_create_todos_pilotos_distintos_aceita():
    trips = [_trip('1P', 1), _trip('2P', 2), _trip('IN', 3), _trip('AL', 4)]
    EtapaCreate(missao_id=1, tripulantes=trips, **_BASE_ETAPA)


def test_etapa_create_1p_duplicado_rejeita():
    trips = [_trip('1P', 1), _trip('1P', 2)]
    with pytest.raises(ValidationError) as exc_info:
        EtapaCreate(missao_id=1, tripulantes=trips, **_BASE_ETAPA)
    assert 'Posicao de piloto duplicada: 1P' in str(exc_info.value)


def test_etapa_create_2p_duplicado_rejeita():
    trips = [_trip('2P', 1), _trip('2P', 2)]
    with pytest.raises(ValidationError) as exc_info:
        EtapaCreate(missao_id=1, tripulantes=trips, **_BASE_ETAPA)
    assert 'Posicao de piloto duplicada: 2P' in str(exc_info.value)


def test_etapa_create_in_duplicado_rejeita():
    trips = [_trip('IN', 1), _trip('IN', 2)]
    with pytest.raises(ValidationError) as exc_info:
        EtapaCreate(missao_id=1, tripulantes=trips, **_BASE_ETAPA)
    assert 'Posicao de piloto duplicada: IN' in str(exc_info.value)


def test_etapa_create_al_duplicado_rejeita():
    trips = [_trip('AL', 1), _trip('AL', 2)]
    with pytest.raises(ValidationError) as exc_info:
        EtapaCreate(missao_id=1, tripulantes=trips, **_BASE_ETAPA)
    assert 'Posicao de piloto duplicada: AL' in str(exc_info.value)


# ---------------------------------------------------------------------------
# EtapaCreateNested
# ---------------------------------------------------------------------------


def test_etapa_create_nested_duplicado_rejeita():
    trips = [_trip('1P', 1), _trip('1P', 2)]
    with pytest.raises(ValidationError) as exc_info:
        EtapaCreateNested(tripulantes=trips, **_BASE_ETAPA)
    assert 'Posicao de piloto duplicada: 1P' in str(exc_info.value)


def test_etapa_create_nested_distintos_aceita():
    trips = [_trip('1P', 1), _trip('2P', 2)]
    EtapaCreateNested(tripulantes=trips, **_BASE_ETAPA)


# ---------------------------------------------------------------------------
# EtapaUpdateNested
# ---------------------------------------------------------------------------


def test_etapa_update_nested_duplicado_rejeita():
    trips = [_trip('2P', 1), _trip('2P', 2)]
    with pytest.raises(ValidationError) as exc_info:
        EtapaUpdateNested(id=10, tripulantes=trips, **_BASE_ETAPA)
    assert 'Posicao de piloto duplicada: 2P' in str(exc_info.value)


def test_etapa_update_nested_distintos_aceita():
    trips = [_trip('1P', 1), _trip('2P', 2)]
    EtapaUpdateNested(id=10, tripulantes=trips, **_BASE_ETAPA)


# ---------------------------------------------------------------------------
# EtapaUpdate (campos opcionais)
# ---------------------------------------------------------------------------


def test_etapa_update_sem_tripulantes_aceita():
    EtapaUpdate()


def test_etapa_update_pilotos_distintos_aceita():
    trips = [_trip('1P', 1), _trip('IN', 2)]
    EtapaUpdate(tripulantes=trips)


def test_etapa_update_duplicado_rejeita():
    trips = [_trip('IN', 1), _trip('IN', 2)]
    with pytest.raises(ValidationError) as exc_info:
        EtapaUpdate(tripulantes=trips)
    assert 'Posicao de piloto duplicada: IN' in str(exc_info.value)


# ---------------------------------------------------------------------------
# Garantia: outras funcoes nao sao afetadas
# ---------------------------------------------------------------------------


def test_outras_funcoes_nao_sao_validadas():
    """Funcoes nao-piloto com func_bordo identico nao devem ser barradas."""
    trips = [
        TripEtapaIn(trip_id=1, func='mc', func_bordo='MC'),
        TripEtapaIn(trip_id=2, func='mc', func_bordo='MC'),
    ]
    EtapaCreate(missao_id=1, tripulantes=trips, **_BASE_ETAPA)
