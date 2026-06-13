"""Domínio de custos de missão/comissionamento.

Reúne tudo que materializa, lê e verifica o cache de custos (`FragMis.custos`),
antes espalhado entre `utils/financeiro.py` e `services/financeiro.py`.

Submódulos:
- `calculo`: materialização do JSONB de custos (cálculo puro, sem I/O).
- `leitura`: montagem do cache pré-calculado para o frontend.
- `integridade`: chave canônica pg+sit, hash e verificação de drift.
- `cache_ref`: caches de referência (diárias, soldos, grupos).

Fluxo: `carregar_caches_custo` -> `calcular_custos_frag_mis` (grava em
`custos`, com `_input_hash`) -> `custo_missao` (lê). A função
`verificar_integridade_custos` compara o hash atual com o armazenado.
"""

from fcontrol_api.services.custos.cache_ref import (
    cache_diarias,
    cache_soldos,
    carregar_caches_custo,
)
from fcontrol_api.services.custos.calculo import calcular_custos_frag_mis
from fcontrol_api.services.custos.integridade import (
    gerar_hash_custos,
    verificar_integridade_custos,
)
from fcontrol_api.services.custos.leitura import custo_missao

__all__ = [
    'cache_diarias',
    'cache_soldos',
    'calcular_custos_frag_mis',
    'carregar_caches_custo',
    'custo_missao',
    'gerar_hash_custos',
    'verificar_integridade_custos',
]
