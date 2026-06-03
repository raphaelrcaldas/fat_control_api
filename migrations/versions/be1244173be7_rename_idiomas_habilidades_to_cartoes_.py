"""rename idiomas_habilidades to cartoes, add cvi, rename resource

Revision ID: be1244173be7
Revises: 644c5a6b323d
Create Date: 2026-06-03 13:34:16.469672

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'be1244173be7'
down_revision: Union[str, None] = '644c5a6b323d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table(
        'idiomas_habilidades', 'cartoes', schema='instrucao'
    )
    op.add_column(
        'cartoes',
        sa.Column('cvi_validade', sa.Date(), nullable=True),
        schema='instrucao',
    )
    op.execute(
        "UPDATE security.resources "
        "SET name = 'cartoes', "
        "description = 'cartoes do piloto (idiomas e CVI)' "
        "WHERE name = 'idiomas'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE security.resources "
        "SET name = 'idiomas', "
        "description = 'tabela idiomas proficiencia' "
        "WHERE name = 'cartoes'"
    )
    op.drop_column('cartoes', 'cvi_validade', schema='instrucao')
    op.rename_table(
        'cartoes', 'idiomas_habilidades', schema='instrucao'
    )
