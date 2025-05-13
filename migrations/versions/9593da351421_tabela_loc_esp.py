"""tabela loc esp

Revision ID: 9593da351421
Revises: 437734bf2a2a
Create Date: 2025-05-13 19:04:10.143353

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9593da351421'
down_revision: Union[str, None] = '437734bf2a2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('grupos_loc_esp',
    sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
    sa.Column('cidade_id', sa.Integer(), nullable=False),
    sa.Column('grupo', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['cidade_id'], ['cidades.codigo'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('grupos_loc_esp')
