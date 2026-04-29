"""add data_expedicao columns and check constraints to passaportes

Revision ID: e32b8c7a4684
Revises: 93742dc1532f
Create Date: 2026-04-29 05:48:23.373207

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e32b8c7a4684'
down_revision: Union[str, None] = '93742dc1532f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'passaportes',
        sa.Column('data_expedicao_passaporte', sa.Date(), nullable=True),
        schema='inteligencia',
    )
    op.add_column(
        'passaportes',
        sa.Column('data_expedicao_visa', sa.Date(), nullable=True),
        schema='inteligencia',
    )
    op.create_check_constraint(
        'ck_passaporte_expedicao_le_validade',
        'passaportes',
        'data_expedicao_passaporte IS NULL '
        'OR validade_passaporte IS NULL '
        'OR data_expedicao_passaporte <= validade_passaporte',
        schema='inteligencia',
    )
    op.create_check_constraint(
        'ck_visa_expedicao_le_validade',
        'passaportes',
        'data_expedicao_visa IS NULL '
        'OR validade_visa IS NULL '
        'OR data_expedicao_visa <= validade_visa',
        schema='inteligencia',
    )


def downgrade() -> None:
    op.drop_constraint(
        'ck_visa_expedicao_le_validade',
        'passaportes',
        type_='check',
        schema='inteligencia',
    )
    op.drop_constraint(
        'ck_passaporte_expedicao_le_validade',
        'passaportes',
        type_='check',
        schema='inteligencia',
    )
    op.drop_column(
        'passaportes', 'data_expedicao_visa', schema='inteligencia'
    )
    op.drop_column(
        'passaportes', 'data_expedicao_passaporte', schema='inteligencia'
    )
