"""
Testes para validacoes dos schemas de tripulantes.

Testa as validacoes de:
- Trigrama (apenas letras, 3 caracteres)
"""

import pytest
from pydantic import ValidationError

from fcontrol_api.schemas.ops.tripulantes import BaseTrip, TripSchema


def test_trig_valido_aceito():
    """Trigrama com 3 letras deve ser aceito."""
    trip = BaseTrip(trig='abc')
    assert trip.trig == 'abc'


def test_trig_maiusculo_normalizado():
    """Trigrama em maiusculas deve ser normalizado para minusculas."""
    trip = BaseTrip(trig='ABC')
    assert trip.trig == 'abc'


def test_trig_com_numeros_rejeitado():
    """Trigrama com numeros deve ser rejeitado."""
    with pytest.raises(ValidationError) as exc_info:
        BaseTrip(trig='ab1')
    assert 'Trigrama deve conter apenas letras' in str(exc_info.value)


def test_trig_apenas_numeros_rejeitado():
    """Trigrama apenas com numeros deve ser rejeitado."""
    with pytest.raises(ValidationError) as exc_info:
        BaseTrip(trig='123')
    assert 'Trigrama deve conter apenas letras' in str(exc_info.value)


def test_trig_com_caracteres_especiais_rejeitado():
    """Trigrama com caracteres especiais deve ser rejeitado."""
    with pytest.raises(ValidationError) as exc_info:
        BaseTrip(trig='ab@')
    assert 'Trigrama deve conter apenas letras' in str(exc_info.value)


def test_trig_com_espacos_rejeitado():
    """Trigrama com espacos deve ser rejeitado."""
    with pytest.raises(ValidationError) as exc_info:
        BaseTrip(trig='a b')
    assert 'Trigrama deve conter apenas letras' in str(exc_info.value)


def test_trig_muito_curto_rejeitado():
    """Trigrama com menos de 3 caracteres deve ser rejeitado."""
    with pytest.raises(ValidationError) as exc_info:
        BaseTrip(trig='ab')
    assert 'trig' in str(exc_info.value).lower()


def test_trig_muito_longo_rejeitado():
    """Trigrama com mais de 3 caracteres deve ser rejeitado."""
    with pytest.raises(ValidationError) as exc_info:
        BaseTrip(trig='abcd')
    assert 'trig' in str(exc_info.value).lower()


def test_trip_schema_trig_valido():
    """Trigrama valido deve ser aceito em TripSchema."""
    trip = TripSchema(trig='abc', user_id=1, uae='11gt')
    assert trip.trig == 'abc'


def test_trip_schema_trig_com_numeros_rejeitado():
    """Trigrama com numeros deve ser rejeitado em TripSchema."""
    with pytest.raises(ValidationError) as exc_info:
        TripSchema(trig='ab1', user_id=1, uae='11gt')
    assert 'Trigrama deve conter apenas letras' in str(exc_info.value)
