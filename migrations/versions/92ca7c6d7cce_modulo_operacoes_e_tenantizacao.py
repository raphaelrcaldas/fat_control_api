"""modulo operacoes e tenantizacao

Revision ID: 92ca7c6d7cce
Revises: 0c4c4b16398e
Create Date: 2026-06-10 16:09:46.970505

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '92ca7c6d7cce'
down_revision: Union[str, None] = '0c4c4b16398e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Backfill: todo o acervo legado pertence à única unidade tenant
# existente ('11gt'); não há vínculo nos dados que permita derivar outra
# org (users são universais).
_LEGACY_UAE = '11gt'

# Tabelas existentes que recebem `uae` NOT NULL com backfill '11gt'.
# (tabela, schema) — schema None = public.
_UAE_11GT_TABLES = (
    ('om_etiquetas', None),
    ('comissionamento', 'cegep'),
    ('etiqueta', 'cegep'),
    ('frag_mis', 'cegep'),
)

# Backfill da org de cada missão: org mais comum (mode) entre os
# tripulantes das suas etapas. Vínculo missão->org é indireto
# (missao <- etapas <- trip_etapa -> tripulantes.uae).
_BACKFILL_MISSAO_UAE = """
    UPDATE estatistica.missao AS m
    SET uae = sub.uae
    FROM (
        SELECT e.missao_id,
               mode() WITHIN GROUP (ORDER BY t.uae) AS uae
        FROM estatistica.etapas AS e
        JOIN estatistica.trip_etapa AS te ON te.etapa_id = e.id
        JOIN tripulantes AS t ON t.id = te.trip_id
        GROUP BY e.missao_id
    ) AS sub
    WHERE m.id = sub.missao_id
"""


def _retarget_uae_to_tenants(table: str, new_name: str) -> None:
    """Reaponta a FK de `uae`: organizacoes.sigla -> tenants.organizacao_id.

    O nome da constraint de origem varia entre ambientes (dev x prod,
    por causa de stamp vs. execução do baseline), então é descoberto via
    introspecção em vez de hardcoded.
    """
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for fk in insp.get_foreign_keys(table):
        if 'uae' in (fk.get('constrained_columns') or []):
            op.drop_constraint(fk['name'], table, type_='foreignkey')
    op.create_foreign_key(
        new_name,
        table,
        'tenants',
        ['uae'],
        ['organizacao_id'],
        onupdate='CASCADE',
        ondelete='RESTRICT',
    )


def upgrade() -> None:
    # --- Catálogo de projetos + seed (necessário antes das FKs que o
    #     referenciam: aeronaves.projeto NOT NULL server_default 'C8' e
    #     trip_funcs.proj, que já guarda o modelo 'kc-390').
    op.create_table('projetos_anvs',
    sa.Column('id_projeto', sa.String(length=2), nullable=False),
    sa.Column('modelo', sa.String(length=20), nullable=False),
    sa.PrimaryKeyConstraint('id_projeto'),
    sa.UniqueConstraint('modelo')
    )
    op.execute(
        "INSERT INTO projetos_anvs (id_projeto, modelo) "
        "VALUES ('C8', 'kc-390')"
    )

    # --- Módulo Operações
    op.create_table('operacoes',
    sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
    sa.Column('numero', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=120), nullable=False),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('cidade_id', sa.Integer(), nullable=False),
    sa.Column('data_inicio', sa.Date(), nullable=False),
    sa.Column('data_fim', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('uae', sa.String(length=20), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('documento_referencia', sa.String(length=100), nullable=True),
    sa.Column('obs', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('planejada', 'andamento', 'encerrada', 'cancelada')", name='ck_operacao_status'),
    sa.CheckConstraint("tipo IN ('operacao', 'manobra', 'exercicio')", name='ck_operacao_tipo'),
    sa.CheckConstraint('data_fim >= data_inicio', name='ck_operacao_periodo'),
    sa.ForeignKeyConstraint(['cidade_id'], ['cidades.codigo'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['uae'], ['tenants.organizacao_id'], onupdate='CASCADE', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('uae', 'nome', name='uq_operacao_uae_nome'),
    sa.UniqueConstraint('uae', 'numero', name='uq_operacao_uae_numero')
    )
    op.create_table('tenant_projetos',
    sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
    sa.Column('uae', sa.String(length=20), nullable=False),
    sa.Column('projeto', sa.String(length=2), nullable=False),
    sa.ForeignKeyConstraint(['projeto'], ['projetos_anvs.id_projeto'], name='fk_tenant_projetos_projeto', onupdate='CASCADE', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['uae'], ['tenants.organizacao_id'], name='fk_tenant_projetos_uae', onupdate='CASCADE', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('uae', 'projeto', name='uq_tenant_projeto')
    )
    op.create_table('operacao_pessoal',
    sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
    sa.Column('operacao_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('func', sa.String(length=80), nullable=False),
    sa.Column('om', sa.String(length=60), nullable=False),
    sa.Column('data_ingresso', sa.Date(), nullable=False),
    sa.Column('data_regresso', sa.Date(), nullable=False),
    sa.CheckConstraint('data_regresso >= data_ingresso', name='ck_operacao_pessoal_periodo'),
    sa.ForeignKeyConstraint(['operacao_id'], ['operacoes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('operacao_id', 'user_id', name='uq_operacao_pessoal_user')
    )
    op.create_index(op.f('ix_operacao_pessoal_operacao_id'), 'operacao_pessoal', ['operacao_id'], unique=False)
    op.create_table('operacao_etapa',
    sa.Column('etapa_id', sa.Integer(), nullable=False),
    sa.Column('operacao_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['etapa_id'], ['estatistica.etapas.id'], name='fk_operacao_etapa_etapa', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['operacao_id'], ['operacoes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('etapa_id')
    )
    op.create_index(op.f('ix_operacao_etapa_operacao_id'), 'operacao_etapa', ['operacao_id'], unique=False)

    # --- aeronaves.projeto (server_default 'C8' backfilla as existentes,
    #     que precisam satisfazer a FK) + FKs ao catálogo.
    op.add_column('aeronaves', sa.Column('projeto', sa.String(length=2), server_default='C8', nullable=False))
    op.create_foreign_key('fk_aeronaves_projeto', 'aeronaves', 'projetos_anvs', ['projeto'], ['id_projeto'], onupdate='CASCADE')
    op.create_foreign_key('fk_trip_funcs_proj', 'trip_funcs', 'projetos_anvs', ['proj'], ['modelo'], onupdate='CASCADE')

    # --- Backfill tenant_projetos: a única unidade ('11gt') passa a
    #     operar os projetos que já tem em frota (derivado das aeronaves).
    op.execute(
        'INSERT INTO tenant_projetos (uae, projeto) '
        f"SELECT '{_LEGACY_UAE}', a.projeto "
        'FROM (SELECT DISTINCT projeto FROM aeronaves) a'
    )

    # --- users.data_praca (data de ingresso na força; opcional)
    op.add_column('users', sa.Column('data_praca', sa.Date(), nullable=True))

    # --- Retarget das FKs uae: organizacoes.sigla -> tenants.organizacao_id.
    #     Nome da constraint de origem descoberto por introspecção (varia
    #     entre dev/prod), não hardcoded.
    _retarget_uae_to_tenants('tripulantes', 'fk_tripulantes_uae_tenants')
    _retarget_uae_to_tenants('quads_group', 'fk_quads_group_uae_tenants')
    _retarget_uae_to_tenants('om_ordens_missao', 'fk_om_ordens_missao_uae_tenants')

    # --- uae NOT NULL em tabelas com dados: nullable -> backfill -> trava
    for tabela, schema in _UAE_11GT_TABLES:
        op.add_column(tabela, sa.Column('uae', sa.String(length=20), nullable=True), schema=schema)
        alvo = f'{schema}.{tabela}' if schema else tabela
        op.execute(f"UPDATE {alvo} SET uae = '{_LEGACY_UAE}'")
        op.alter_column(tabela, 'uae', existing_type=sa.String(length=20), nullable=False, schema=schema)
        op.create_foreign_key(f'fk_{tabela}_uae_tenants', tabela, 'tenants', ['uae'], ['organizacao_id'], source_schema=schema, onupdate='CASCADE', ondelete='RESTRICT')

    # --- esf_aer_alocado.uae: alocação SAGEM por unidade (+ unique por
    #     esforço/ano/org). Catálogo EsforcoAereo permanece global.
    op.add_column('esf_aer_alocado', sa.Column('uae', sa.String(length=20), nullable=True), schema='estatistica')
    op.execute(f"UPDATE estatistica.esf_aer_alocado SET uae = '{_LEGACY_UAE}'")
    op.alter_column('esf_aer_alocado', 'uae', existing_type=sa.String(length=20), nullable=False, schema='estatistica')
    op.create_unique_constraint('uq_esf_aer_aloc_org_ano', 'esf_aer_alocado', ['esfaer_id', 'ano_ref', 'uae'], schema='estatistica')
    op.create_foreign_key('fk_esf_aer_alocado_uae', 'esf_aer_alocado', 'tenants', ['uae'], ['organizacao_id'], source_schema='estatistica', onupdate='CASCADE', ondelete='RESTRICT')

    # --- missao.uae: backfill pela org mais comum das etapas da missão
    op.add_column('missao', sa.Column('uae', sa.String(length=20), nullable=True), schema='estatistica')
    op.execute(_BACKFILL_MISSAO_UAE)
    # Fallback: missões sem etapas/tripulantes (ou órfãs) não resolvem
    # pela query acima — caem no tenant legado para satisfazer o NOT NULL.
    op.execute(
        "UPDATE estatistica.missao SET uae = '%s' WHERE uae IS NULL"
        % _LEGACY_UAE
    )
    op.alter_column('missao', 'uae', existing_type=sa.String(length=20), nullable=False, schema='estatistica')
    op.create_foreign_key('fk_missao_uae_tenants', 'missao', 'tenants', ['uae'], ['organizacao_id'], source_schema='estatistica', onupdate='CASCADE', ondelete='RESTRICT')


def downgrade() -> None:
    op.drop_constraint('fk_missao_uae_tenants', 'missao', schema='estatistica', type_='foreignkey')
    op.drop_column('missao', 'uae', schema='estatistica')

    op.drop_constraint('fk_esf_aer_alocado_uae', 'esf_aer_alocado', schema='estatistica', type_='foreignkey')
    op.drop_constraint('uq_esf_aer_aloc_org_ano', 'esf_aer_alocado', schema='estatistica', type_='unique')
    op.drop_column('esf_aer_alocado', 'uae', schema='estatistica')

    for tabela, schema in reversed(_UAE_11GT_TABLES):
        op.drop_constraint(f'fk_{tabela}_uae_tenants', tabela, schema=schema, type_='foreignkey')
        op.drop_column(tabela, 'uae', schema=schema)

    op.drop_constraint('fk_om_ordens_missao_uae_tenants', 'om_ordens_missao', type_='foreignkey')
    op.create_foreign_key(op.f('fk_om_ordens_missao_uae_organizacoes'), 'om_ordens_missao', 'organizacoes', ['uae'], ['sigla'], onupdate='CASCADE', ondelete='RESTRICT')
    op.drop_constraint('fk_quads_group_uae_tenants', 'quads_group', type_='foreignkey')
    op.create_foreign_key(op.f('fk_quads_group_uae_organizacoes'), 'quads_group', 'organizacoes', ['uae'], ['sigla'], onupdate='CASCADE', ondelete='RESTRICT')
    op.drop_constraint('fk_tripulantes_uae_tenants', 'tripulantes', type_='foreignkey')
    op.create_foreign_key(op.f('fk_tripulantes_uae_organizacoes'), 'tripulantes', 'organizacoes', ['uae'], ['sigla'], onupdate='CASCADE', ondelete='RESTRICT')

    op.drop_column('users', 'data_praca')

    op.drop_constraint('fk_trip_funcs_proj', 'trip_funcs', type_='foreignkey')
    op.drop_constraint('fk_aeronaves_projeto', 'aeronaves', type_='foreignkey')
    op.drop_column('aeronaves', 'projeto')

    op.drop_index(op.f('ix_operacao_etapa_operacao_id'), table_name='operacao_etapa')
    op.drop_table('operacao_etapa')
    op.drop_index(op.f('ix_operacao_pessoal_operacao_id'), table_name='operacao_pessoal')
    op.drop_table('operacao_pessoal')
    op.drop_table('tenant_projetos')
    op.drop_table('operacoes')
    op.drop_table('projetos_anvs')
