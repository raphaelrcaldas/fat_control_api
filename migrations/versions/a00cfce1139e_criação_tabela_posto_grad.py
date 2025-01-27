"""criação tabela posto_grad

Revision ID: a00cfce1139e
Revises: 45705ff1df74
Create Date: 2025-01-27 11:34:38.885658

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a00cfce1139e'
down_revision: Union[str, None] = '45705ff1df74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('posto_grad',
    sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
    sa.Column('ant', sa.Integer(), nullable=False),
    sa.Column('short', sa.String(), nullable=False),
    sa.Column('mid', sa.String(), nullable=False),
    sa.Column('long', sa.String(), nullable=False),
    sa.Column('soldo', sa.Float(), nullable=False),
    sa.Column('circulo', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('posto_grad')
