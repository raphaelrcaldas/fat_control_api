"""adiciona uae ao orcamento_anual

Revision ID: ba824d743f2c
Revises: 933dd913724d
Create Date: 2026-07-11 11:28:54.891072

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ba824d743f2c'
down_revision: Union[str, None] = '933dd913724d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Backfill: o orçamento anual, até aqui global, passa a ser por org.
# O acervo legado (cadastrado antes da tenantização) pertence à única
# unidade que hoje usa o recurso.
_LEGACY_UAE = '11gt'


def upgrade() -> None:
    # nullable=True para o backfill; trava NOT NULL depois de povoar.
    op.add_column(
        'orcamento_anual',
        sa.Column('uae', sa.String(length=20), nullable=True),
        schema='cegep',
    )
    op.execute(
        f"UPDATE cegep.orcamento_anual SET uae = '{_LEGACY_UAE}' "
        'WHERE uae IS NULL'
    )
    op.alter_column(
        'orcamento_anual',
        'uae',
        existing_type=sa.String(length=20),
        nullable=False,
        schema='cegep',
    )
    op.drop_constraint(
        op.f('uq_orcamento_anual_ano_ref'),
        'orcamento_anual',
        schema='cegep',
        type_='unique',
    )
    op.create_unique_constraint(
        'uq_orcamento_anual_uae_ano_ref',
        'orcamento_anual',
        ['uae', 'ano_ref'],
        schema='cegep',
    )
    op.create_foreign_key(
        'fk_orcamento_anual_uae_tenants',
        'orcamento_anual',
        'tenants',
        ['uae'],
        ['organizacao_id'],
        source_schema='cegep',
        onupdate='CASCADE',
        ondelete='RESTRICT',
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_orcamento_anual_uae_tenants',
        'orcamento_anual',
        schema='cegep',
        type_='foreignkey',
    )
    op.drop_constraint(
        'uq_orcamento_anual_uae_ano_ref',
        'orcamento_anual',
        schema='cegep',
        type_='unique',
    )
    op.create_unique_constraint(
        op.f('uq_orcamento_anual_ano_ref'),
        'orcamento_anual',
        ['ano_ref'],
        schema='cegep',
        postgresql_nulls_not_distinct=False,
    )
    op.drop_column('orcamento_anual', 'uae', schema='cegep')
