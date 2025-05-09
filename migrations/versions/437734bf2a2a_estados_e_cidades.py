"""estados e cidades

Revision ID: 437734bf2a2a
Revises: cbcf68a2d6f1
Create Date: 2025-05-09 17:17:11.849357

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '437734bf2a2a'
down_revision: Union[str, None] = 'cbcf68a2d6f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('estados',
    sa.Column('codigo_uf', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(), nullable=False),
    sa.Column('uf', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('uf')
    )
    op.create_table('cidades',
    sa.Column('codigo', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(), nullable=False),
    sa.Column('uf', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['uf'], ['estados.uf'], ),
    sa.PrimaryKeyConstraint('codigo')
    )


def downgrade() -> None:
    op.drop_table('cidades')
    op.drop_table('estados')
