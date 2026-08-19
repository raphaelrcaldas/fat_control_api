"""Seed das funções operadas por cada org de teste.

O catálogo global (`funcoes` + `funcoes_posicoes`) já vem da migration
`a826ee3bcd9e` — aqui só se declara o que cada unidade opera, que é o
conjunto que o write-path de tripulante e de quadrinhos valida. As duas
orgs operam todas as funções para não restringir os testes existentes; os
testes de escopo montam seus próprios recortes.
"""

from fcontrol_api.models.shared.funcoes import FuncaoUae

CODIGOS = ['pil', 'oe', 'mc', 'lm', 'tf', 'os', 'md', 'ml']

FUNCOES_UAE = [
    FuncaoUae(uae=uae, func_cod=cod)
    for uae in ('11gt', '1gt')
    for cod in CODIGOS
]
