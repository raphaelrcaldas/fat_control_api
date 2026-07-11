from datetime import date
from typing import Annotated, Literal

from fastapi import Body
from pydantic import BaseModel, ConfigDict

# =============================================================================
# TIPOS BASE
# =============================================================================

opers = Literal['ba', 'op', 'in', 'al']
funcs = Literal['pil', 'mc', 'lm', 'oe', 'os', 'tf', 'ml', 'md']

# =============================================================================
# POSIÇÕES A BORDO
# =============================================================================

# Posições por função
PosicoesPiloto = Literal['1P', '2P', 'IN', 'AL']
PosicoesMecanico = Literal['MC', 'IC', 'AC']
PosicoesLoadmaster = Literal['LM', 'IG', 'AG']
PosicoesOE = Literal['O3', 'I3', 'A3']
PosicoesOS = Literal['OS', 'IS', 'AS']
PosicoesComissario = Literal['TF', 'IF', 'AF']

# Todas as posições válidas (para validação genérica)
FuncBordo = Literal[
    '1P',
    '2P',
    'IN',
    'AL',  # pil
    'MC',
    'IC',
    'AC',  # mc
    'LM',
    'IG',
    'AG',  # lm
    'O3',
    'I3',
    'A3',  # oe
    'OS',
    'IS',
    'AS',  # os
    'TF',
    'IF',
    'AF',  # tf
]

# Mapeamento função → posições válidas (para validação condicional)
POSICOES_POR_FUNC: dict[str, tuple[str, ...]] = {
    'pil': ('1P', '2P', 'IN', 'AL'),
    'mc': ('MC', 'IC', 'AC'),
    'lm': ('LM', 'IG', 'AG'),
    'oe': ('O3', 'I3', 'A3'),
    'os': ('OS', 'IS', 'AS'),
    'tf': ('TF', 'IF', 'AF'),
    'ml': (),  # Função esporádica, sem controle
    'md': (),  # Função esporádica, sem controle
}


def is_posicao_valida(func: str, posicao: str) -> bool:
    """Verifica se uma posição é válida para uma função."""
    posicoes = POSICOES_POR_FUNC.get(func, ())
    return posicao in posicoes


class BaseFunc(BaseModel):
    """Campos de função do tripulante (colunas de `tripulantes`)."""

    func: funcs
    oper: opers
    # FK para `projetos_anvs.modelo`: o catálogo é dinâmico e o conjunto
    # válido depende da org (tenant_projetos), então a checagem é feita na
    # rota contra os projetos da org ativa, não por Literal fechado aqui.
    proj: str
    data_op: Annotated[date | None, Body()] = None
    model_config = ConfigDict(from_attributes=True)
