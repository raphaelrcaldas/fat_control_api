from . import (
    aeronaves,
    estados_cidades,
    funcoes,
    indisp,
    om,
    organizacao,
    posto_grad,
    quads,
    tenant,
    tripulantes,
    users,
)

# `operacao` é importado de propósito FORA deste __init__: ele referencia
# `estatistica.Etapa` (FK cross-Base em OperacaoEtapa) e, como `etapa` importa
# `shared.aeronaves` (disparando este __init__), incluí-lo aqui criaria um
# import circular. É registrado explicitamente em `migrations/env.py` e
# carregado em runtime pelo router `ops/operacoes`.
