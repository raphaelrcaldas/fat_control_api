"""add remuneracao mes_ano aux_transp to dados_bancarios

Revision ID: 41408c0ce2c0
Revises: f75b32a52903
Create Date: 2026-05-25 19:05:56.909474

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '41408c0ce2c0'
down_revision: Union[str, None] = 'f75b32a52903'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'dados_bancarios',
        sa.Column(
            'remuneracao',
            sa.Numeric(precision=14, scale=2),
            nullable=True,
        ),
        schema='cegep',
    )
    op.add_column(
        'dados_bancarios',
        sa.Column('mes_ano', sa.Date(), nullable=True),
        schema='cegep',
    )
    op.add_column(
        'dados_bancarios',
        sa.Column(
            'aux_transp',
            sa.Numeric(precision=14, scale=2),
            nullable=True,
        ),
        schema='cegep',
    )
    op.alter_column(
        'dados_bancarios',
        'created_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        server_default=sa.func.now(),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
        schema='cegep',
    )
    op.alter_column(
        'dados_bancarios',
        'updated_at',
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        nullable=True,
        postgresql_using="updated_at AT TIME ZONE 'UTC'",
        schema='cegep',
    )


def downgrade() -> None:
    op.alter_column(
        'dados_bancarios',
        'updated_at',
        existing_type=sa.DateTime(timezone=True),
        type_=postgresql.TIMESTAMP(),
        nullable=False,
        schema='cegep',
    )
    op.alter_column(
        'dados_bancarios',
        'created_at',
        existing_type=sa.DateTime(timezone=True),
        type_=postgresql.TIMESTAMP(),
        existing_nullable=False,
        server_default=None,
        schema='cegep',
    )
    op.drop_column('dados_bancarios', 'aux_transp', schema='cegep')
    op.drop_column('dados_bancarios', 'mes_ano', schema='cegep')
    op.drop_column('dados_bancarios', 'remuneracao', schema='cegep')
