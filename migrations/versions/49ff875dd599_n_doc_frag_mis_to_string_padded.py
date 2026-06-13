"""n_doc_frag_mis_to_string_padded

Revision ID: 49ff875dd599
Revises: a82acc4794d2
Create Date: 2026-06-13 12:53:08.553933

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '49ff875dd599'
down_revision: Union[str, None] = 'a82acc4794d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # int -> varchar(10), preenchendo zeros à esquerda (mín. 3 dígitos).
    # USING explícito é necessário: o cast padrão não aplica o padding.
    # O alvo do lpad é greatest(3, length) para NÃO truncar os números
    # maiores que 3 dígitos (há ordens reais de 4 dígitos): lpad trunca
    # quando o texto excede o comprimento alvo.
    op.alter_column(
        'frag_mis',
        'n_doc',
        existing_type=sa.Integer(),
        type_=sa.String(length=10),
        existing_nullable=False,
        postgresql_using=(
            "lpad(n_doc::text, greatest(3, length(n_doc::text)), '0')"
        ),
        schema='cegep',
    )


def downgrade() -> None:
    op.alter_column(
        'frag_mis',
        'n_doc',
        existing_type=sa.String(length=10),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using='n_doc::integer',
        schema='cegep',
    )
