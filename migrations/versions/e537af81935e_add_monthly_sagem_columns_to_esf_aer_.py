"""add monthly sagem columns to esf_aer_alocado

Revision ID: e537af81935e
Revises: cd008c17ffd9
Create Date: 2026-03-21 18:34:49.982274

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e537af81935e'
down_revision: Union[str, None] = 'cd008c17ffd9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for i in range(1, 13):
        op.add_column(
            'esf_aer_alocado',
            sa.Column(
                f'm{i}',
                sa.SmallInteger(),
                nullable=False,
                server_default=sa.text('0'),
            ),
            schema='estatistica',
        )
        op.create_check_constraint(
            f'ck_aloc_m{i}',
            'esf_aer_alocado',
            f'm{i} >= 0 AND m{i} % 5 = 0',
            schema='estatistica',
        )


def downgrade() -> None:
    for i in range(12, 0, -1):
        op.drop_constraint(
            f'ck_aloc_m{i}',
            'esf_aer_alocado',
            schema='estatistica',
        )
        op.drop_column(
            'esf_aer_alocado', f'm{i}', schema='estatistica'
        )
