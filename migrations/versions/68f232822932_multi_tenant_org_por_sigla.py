"""multi-tenant org por sigla

Revision ID: 68f232822932
Revises: 41408c0ce2c0
Create Date: 2026-06-01 19:59:22.503869

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '68f232822932'
down_revision: Union[str, None] = '41408c0ce2c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Diretorio inicial de organizacoes (fonte: unidadeOptions do client).
# Cobre os codigos hoje em uso em users.unidade / tripulantes.uae etc.
# sigla = PK (codigo); sigla_3 = rotulo de exibicao (mesmo valor em nome,
# que e NOT NULL). sigla_2 fica NULL (admin preenche depois via UI).
SEED_ORGS = [
    {'sigla': '11gt', 'nome': '1º/1º GT', 'sigla_3': '1º/1º GT'},
    {'sigla': '12gt', 'nome': '1º/2º GT', 'sigla_3': '1º/2º GT'},
    {'sigla': '22gt', 'nome': '2º/2º GT', 'sigla_3': '2º/2º GT'},
    {'sigla': 'eta3', 'nome': '3º ETA', 'sigla_3': '3º ETA'},
    {'sigla': 'bagl', 'nome': 'BAGL', 'sigla_3': 'BAGL'},
    {'sigla': 'glog', 'nome': 'GLOG', 'sigla_3': 'GLOG'},
    {'sigla': 'gsd_gl', 'nome': 'GSD-GL', 'sigla_3': 'GSD-GL'},
    {'sigla': 'pama_gl', 'nome': 'PAMA-GL', 'sigla_3': 'PAMA-GL'},
    {'sigla': 'ctla', 'nome': 'CTLA', 'sigla_3': 'CTLA'},
    {'sigla': 'gapgl', 'nome': 'GAP-GL', 'sigla_3': 'GAP-GL'},
]


def upgrade() -> None:
    op.create_table(
        'organizacoes',
        sa.Column('sigla', sa.String(length=20), nullable=False),
        sa.Column('nome', sa.String(length=150), nullable=False),
        sa.Column('sigla_2', sa.String(length=20), nullable=True),
        sa.Column('sigla_3', sa.String(length=20), nullable=True),
        sa.Column('alias', sa.String(length=100), nullable=True),
        sa.Column('brasao_path', sa.String(length=255), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('sigla'),
        sa.UniqueConstraint('sigla_2'),
        sa.UniqueConstraint('sigla_3'),
    )

    # Seed do diretorio antes das FKs do data-plane (que referenciam sigla).
    organizacoes = sa.table(
        'organizacoes',
        sa.column('sigla', sa.String),
        sa.column('nome', sa.String),
        sa.column('sigla_3', sa.String),
    )
    op.bulk_insert(organizacoes, SEED_ORGS)

    op.create_table(
        'organizacao_relacoes',
        sa.Column('parent_id', sa.String(length=20), nullable=False),
        sa.Column('child_id', sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            'parent_id <> child_id',
            name='ck_organizacao_relacoes_sem_autoreferencia',
        ),
        sa.ForeignKeyConstraint(
            ['child_id'], ['organizacoes.sigla'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['parent_id'], ['organizacoes.sigla'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('parent_id', 'child_id'),
    )
    op.create_table(
        'tenants',
        sa.Column('organizacao_id', sa.String(length=20), nullable=False),
        sa.Column(
            'active',
            sa.Boolean(),
            server_default=sa.text('true'),
            nullable=False,
        ),
        sa.Column(
            'created_at',
            sa.DateTime(),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['organizacao_id'],
            ['organizacoes.sigla'],
            onupdate='CASCADE',
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('organizacao_id'),
    )

    # FKs do data-plane -> organizacoes.sigla (sem reescrita de valor).
    op.create_foreign_key(
        'fk_om_ordens_missao_uae_organizacoes',
        'om_ordens_missao', 'organizacoes', ['uae'], ['sigla'],
        onupdate='CASCADE', ondelete='RESTRICT',
    )
    op.create_foreign_key(
        'fk_quads_group_uae_organizacoes',
        'quads_group', 'organizacoes', ['uae'], ['sigla'],
        onupdate='CASCADE', ondelete='RESTRICT',
    )
    op.create_foreign_key(
        'fk_tripulantes_uae_organizacoes',
        'tripulantes', 'organizacoes', ['uae'], ['sigla'],
        onupdate='CASCADE', ondelete='RESTRICT',
    )
    # users.unidade: alarga p/ casar com organizacoes.sigla (String(20)).
    op.alter_column(
        'users', 'unidade',
        existing_type=sa.String(length=8),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
    op.create_foreign_key(
        'fk_users_unidade_organizacoes',
        'users', 'organizacoes', ['unidade'], ['sigla'],
        onupdate='CASCADE', ondelete='RESTRICT',
    )

    # Escopo de org nos vinculos de perfil (NULL = sistema).
    op.add_column(
        'user_roles',
        sa.Column('organizacao_id', sa.String(length=20), nullable=True),
        schema='security',
    )
    op.create_unique_constraint(
        'uq_user_roles_user_org', 'user_roles',
        ['user_id', 'organizacao_id'],
        schema='security', postgresql_nulls_not_distinct=True,
    )
    op.create_foreign_key(
        'fk_user_roles_organizacao_id',
        'user_roles', 'tenants', ['organizacao_id'], ['organizacao_id'],
        source_schema='security',
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_user_roles_organizacao_id', 'user_roles',
        schema='security', type_='foreignkey',
    )
    op.drop_constraint(
        'uq_user_roles_user_org', 'user_roles',
        schema='security', type_='unique',
    )
    op.drop_column('user_roles', 'organizacao_id', schema='security')

    op.drop_constraint(
        'fk_users_unidade_organizacoes', 'users', type_='foreignkey'
    )
    op.alter_column(
        'users', 'unidade',
        existing_type=sa.String(length=20),
        type_=sa.String(length=8),
        existing_nullable=False,
    )
    op.drop_constraint(
        'fk_tripulantes_uae_organizacoes', 'tripulantes', type_='foreignkey'
    )
    op.drop_constraint(
        'fk_quads_group_uae_organizacoes', 'quads_group', type_='foreignkey'
    )
    op.drop_constraint(
        'fk_om_ordens_missao_uae_organizacoes',
        'om_ordens_missao', type_='foreignkey',
    )
    op.drop_table('tenants')
    op.drop_table('organizacao_relacoes')
    op.drop_table('organizacoes')
