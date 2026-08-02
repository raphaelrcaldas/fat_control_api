"""
Testes para validacoes dos schemas de tripulantes.

Testa as validacoes de:
- Trigrama (apenas letras, 3 caracteres)

A função virou 1:1 no tripulante, então `BaseTrip` herda `BaseFunc` e exige
`func`/`oper`/`proj`. Os helpers abaixo preenchem esses campos com um valor
válido qualquer para que cada teste isole a validação do trigrama — sem eles,
um teste de rejeição passaria pelo motivo errado (o ValidationError viria dos
campos faltando, não do trigrama).
"""

import pytest
from pydantic import ValidationError

from fcontrol_api.schemas.ops.tripulantes import BaseTrip, TripSchema

# oper='al' (aluno) evita a exigência de `data_op` do validador de BaseTrip.
FUNC_VALIDA = {'func': 'pil', 'oper': 'al', 'proj': 'kc-390'}


def _base_trip(trig: str) -> BaseTrip:
    return BaseTrip(trig=trig, **FUNC_VALIDA)


def _trip_schema(trig: str) -> TripSchema:
    return TripSchema(trig=trig, user_id=1, **FUNC_VALIDA)


def test_trig_valido_aceito():
    """Trigrama com 3 letras deve ser aceito."""
    assert _base_trip('ABC').trig == 'ABC'


def test_trig_minusculo_normalizado():
    """Trigrama em minusculas deve ser normalizado para MAIUSCULAS."""
    assert _base_trip('abc').trig == 'ABC'


def test_trig_com_numeros_rejeitado():
    """Trigrama com numeros deve ser rejeitado."""
    with pytest.raises(ValidationError) as exc_info:
        _base_trip('ab1')
    assert 'Trigrama deve conter apenas letras' in str(exc_info.value)


def test_trig_apenas_numeros_rejeitado():
    """Trigrama apenas com numeros deve ser rejeitado."""
    with pytest.raises(ValidationError) as exc_info:
        _base_trip('123')
    assert 'Trigrama deve conter apenas letras' in str(exc_info.value)


def test_trig_com_caracteres_especiais_rejeitado():
    """Trigrama com caracteres especiais deve ser rejeitado."""
    with pytest.raises(ValidationError) as exc_info:
        _base_trip('ab@')
    assert 'Trigrama deve conter apenas letras' in str(exc_info.value)


def test_trig_com_espacos_rejeitado():
    """Trigrama com espacos deve ser rejeitado."""
    with pytest.raises(ValidationError) as exc_info:
        _base_trip('a b')
    assert 'Trigrama deve conter apenas letras' in str(exc_info.value)


def test_trig_muito_curto_rejeitado():
    """Trigrama com menos de 3 caracteres deve ser rejeitado."""
    with pytest.raises(ValidationError) as exc_info:
        _base_trip('ab')
    assert 'trig' in str(exc_info.value).lower()


def test_trig_muito_longo_rejeitado():
    """Trigrama com mais de 3 caracteres deve ser rejeitado."""
    with pytest.raises(ValidationError) as exc_info:
        _base_trip('abcd')
    assert 'trig' in str(exc_info.value).lower()


def test_trip_schema_trig_valido():
    """Trigrama valido deve ser aceito em TripSchema."""
    assert _trip_schema('abc').trig == 'ABC'


def test_trip_schema_trig_com_numeros_rejeitado():
    """Trigrama com numeros deve ser rejeitado em TripSchema."""
    with pytest.raises(ValidationError) as exc_info:
        _trip_schema('ab1')
    assert 'Trigrama deve conter apenas letras' in str(exc_info.value)
