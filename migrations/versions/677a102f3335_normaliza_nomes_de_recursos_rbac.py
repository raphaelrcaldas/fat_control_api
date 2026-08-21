"""normaliza nomes de recursos rbac

Revision ID: 677a102f3335
Revises: 0ac6c65c50dc
Create Date: 2026-08-21

Os nomes de recurso tinham acumulado quatro convenções ao mesmo tempo
(`cartoes-saude`, `dados_bancarios`, `comiss.propostas`, `sebo`) e o hífen
significava duas coisas diferentes: separador de palavra em `cartoes-saude`
e prefixo de módulo em `instrucao-cartoes`.

Passam todos para `modulo.recurso[.subrecurso]`, com underscore juntando
palavras de um mesmo conceito e o ponto separando níveis de hierarquia. O
schema Pydantic passa a reprovar nome fora do padrão, então esta migration
é a única vez que a base precisa ser corrigida em massa.

Recurso é **dado por ambiente** (nenhuma migration semeia), mas renomear
linha existente é transformação única — por isso vem como migration, e não
como SQL solto: garante que todo ambiente receba na mesma ordem em relação
ao código que passa a usar os nomes novos.

Também alinha os labels de `user_action_logs` que espelhavam um recurso
RBAC. O `access_denied` é gravado com o nome do recurso, então deixar os
dois lados divergentes tiraria esses eventos do histórico das telas.
"""

from alembic import op

revision = '677a102f3335'
down_revision = '0ac6c65c50dc'
branch_labels = None
depends_on = None


# antigo -> novo
RECURSOS = {
    'aeronaves': 'ops.aeronaves',
    'trips': 'ops.tripulantes',
    'quad_ops': 'ops.quadrinhos',
    'quadro-oper': 'ops.quadro',
    'operacoes': 'ops.operacoes',
    'operacoes.etapas': 'ops.operacoes.etapas',
    'operacoes.militar': 'ops.operacoes.militar',
    'ordem_missao': 'ops.ordem_missao',
    'ordem_missao.status': 'ops.ordem_missao.status',
    'indisp_trips': 'ops.indisp',
    'cartoes-saude': 'aeromedica.cartoes',
    'crm': 'seg_voo.crm',
    'comiss': 'cegep.comiss',
    'comiss.propostas': 'cegep.comiss.propostas',
    'dados_bancarios': 'cegep.dados_bancarios',
    'missoes_cegep': 'cegep.missoes',
    'orcamento': 'cegep.orcamento',
    'instrucao-cartoes': 'instrucao.cartoes',
    'instrucao-paop': 'instrucao.paop',
    'instrucao-subprogramas': 'instrucao.subprogramas',
    'simulador': 'instrucao.simulador',
    'etapas': 'estatistica.etapas',
    'esf_aer': 'estatistica.esf_aer',
    'sebo': 'estatistica.sebo',
    'passaportes': 'inteligencia.passaportes',
    'passaporte.image': 'inteligencia.passaportes.imagem',
    'user': 'users',
}

# Labels de log que espelham um recurso RBAC. Os demais (auth, missao,
# comissionamento, user_promo, pwd, orcamento_anual) são de outro namespace
# e ficam como estão.
LOGS = {
    'ordem_missao': 'ops.ordem_missao',
    'indisp': 'ops.indisp',
    'user': 'users',
    'operacoes': 'ops.operacoes',
    'trips': 'ops.tripulantes',
}

# Soldos e diárias migraram para o admin de sistema (require_system_admin);
# o recurso RBAC não gateia mais nada e ficou pendurado sem uso.
ORFAOS = ('soldo', 'diaria')


def _renomeia(mapa: dict[str, str]) -> None:
    # Ordem decrescente pelo nome antigo: renomear 'operacoes' antes de
    # 'operacoes.etapas' não colide (o UPDATE é por igualdade exata), mas a
    # ordem estável deixa o log da migration legível.
    for antigo, novo in sorted(mapa.items(), reverse=True):
        op.execute(
            'UPDATE security.resources '
            f"SET name = '{novo}' WHERE name = '{antigo}'"
        )


def upgrade() -> None:
    _renomeia(RECURSOS)

    for antigo, novo in sorted(LOGS.items(), reverse=True):
        op.execute(
            'UPDATE security.user_action_logs '
            f"SET resource = '{novo}' WHERE resource = '{antigo}'"
        )

    # As permissões e os vínculos de role caem por FK/cascade lógico: apaga
    # role_permissions -> permissions -> resource, nessa ordem.
    lista = ', '.join(f"'{n}'" for n in ORFAOS)
    op.execute(
        'DELETE FROM security.role_permissions WHERE permission_id IN ('
        '  SELECT p.id FROM security.permissions p'
        '  JOIN security.resources r ON r.id = p.resource_id'
        f' WHERE r.name IN ({lista}))'
    )
    op.execute(
        'DELETE FROM security.permissions WHERE resource_id IN ('
        f'  SELECT id FROM security.resources WHERE name IN ({lista}))'
    )
    op.execute(f'DELETE FROM security.resources WHERE name IN ({lista})')


def downgrade() -> None:
    _renomeia({novo: antigo for antigo, novo in RECURSOS.items()})

    for antigo, novo in LOGS.items():
        op.execute(
            'UPDATE security.user_action_logs '
            f"SET resource = '{antigo}' WHERE resource = '{novo}'"
        )

    # `soldo` e `diaria` não voltam: eram linhas mortas, e recriá-las sem os
    # vínculos de role que tinham seria restaurar um estado que não existiu.
