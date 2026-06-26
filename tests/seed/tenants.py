"""Seed de organizações e tenants.

A tenantização (multi-tenant) tornou `uae` uma FK para `tenants`, que por
sua vez referencia `organizacoes.sigla`. Diversos seeds e factories usam o
sigla canônico `'11gt'` como org default; `'1gt'` cobre os casos cross-org.
"""

from fcontrol_api.models.shared.aeronaves import ProjetoAnv, TenantProjeto
from fcontrol_api.models.shared.organizacao import Organizacao
from fcontrol_api.models.shared.tenant import Tenant

ORGANIZACOES = [
    Organizacao(sigla='11gt', nome='Primeiro Esquadrão do Primeiro GT'),
    Organizacao(sigla='1gt', nome='Primeiro Grupo de Transporte'),
]

TENANTS = [
    Tenant(organizacao_id='11gt'),
    Tenant(organizacao_id='1gt'),
]

# 'kc-390' (id 'C8') já é inserido pela migração de tenantização. Aqui
# adicionamos um segundo modelo para os testes de filtro/exclusão por
# projeto (trip_funcs.proj é FK -> projetos_anvs.modelo).
PROJETOS = [
    ProjetoAnv(id_projeto='C1', modelo='c-130'),
]

# Quais projetos cada org opera. O escopo de aeronaves é feito por aqui:
# a org só enxerga/cadastra a frota dos projetos que opera.
# '11gt' opera o kc-390 (C8, da migração); '1gt' opera o c-130 (C1).
TENANT_PROJETOS = [
    TenantProjeto(uae='11gt', projeto='C8'),
    TenantProjeto(uae='1gt', projeto='C1'),
]
