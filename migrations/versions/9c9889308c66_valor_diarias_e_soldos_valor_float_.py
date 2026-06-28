"""valor_diarias e soldos: valor float -> numeric(14,2)

Revision ID: 9c9889308c66
Revises: 1d11900e4658
Create Date: 2026-06-28 13:46:06.564138

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c9889308c66'
down_revision: Union[str, None] = '1d11900e4658'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'valor_diarias',
        'valor',
        existing_type=sa.Float(),
        type_=sa.Numeric(14, 2),
        existing_nullable=False,
        postgresql_using='valor::numeric(14,2)',
        schema='cegep',
    )
    op.alter_column(
        'soldos',
        'valor',
        existing_type=sa.Float(),
        type_=sa.Numeric(14, 2),
        existing_nullable=False,
        postgresql_using='valor::numeric(14,2)',
    )


def downgrade() -> None:
    op.alter_column(
        'soldos',
        'valor',
        existing_type=sa.Numeric(14, 2),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using='valor::double precision',
    )
    op.alter_column(
        'valor_diarias',
        'valor',
        existing_type=sa.Numeric(14, 2),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using='valor::double precision',
        schema='cegep',
    )
