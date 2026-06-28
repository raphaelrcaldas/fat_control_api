"""checkconstraints valor_diarias (valor>=0, ordem datas)

Revision ID: 1d11900e4658
Revises: 8bf590c41600
Create Date: 2026-06-28 13:33:10.404241

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1d11900e4658'
down_revision: Union[str, None] = '8bf590c41600'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        'ck_valor_diarias_valor_nao_negativo',
        'valor_diarias',
        'valor >= 0',
        schema='cegep',
    )
    op.create_check_constraint(
        'ck_valor_diarias_data_inicio_antes_fim',
        'valor_diarias',
        'data_fim IS NULL OR data_inicio < data_fim',
        schema='cegep',
    )


def downgrade() -> None:
    op.drop_constraint(
        'ck_valor_diarias_data_inicio_antes_fim',
        'valor_diarias',
        schema='cegep',
        type_='check',
    )
    op.drop_constraint(
        'ck_valor_diarias_valor_nao_negativo',
        'valor_diarias',
        schema='cegep',
        type_='check',
    )
