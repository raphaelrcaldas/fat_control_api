"""Seed de organizações e tenants.

A tenantização (multi-tenant) tornou `uae` uma FK para `tenants`, que por
sua vez referencia `organizacoes.sigla`. Diversos seeds e factories usam o
sigla canônico `'11gt'` como org default; `'1gt'` cobre os casos cross-org.
"""

from fcontrol_api.models.shared.aeronaves import ProjetoAnv
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
