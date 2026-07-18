"""habilita extensao unaccent para busca sem acento

Revision ID: 4977ff3a42f0
Revises: deec47cf5bb0
Create Date: 2026-07-18 13:07:30.284417

Habilita a extensao `unaccent` do PostgreSQL para permitir busca de
cidades (e afins) insensivel a acentos (ex.: "brasilia" casa "Brasília").
O autogenerate nao emite CREATE EXTENSION, entao a migration e manual —
mesmo padrao usado para `btree_gist` (ver migration do ExcludeConstraint
de vigencia de diarias).
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '4977ff3a42f0'
down_revision: Union[str, None] = 'deec47cf5bb0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS unaccent')


def downgrade() -> None:
    op.execute('DROP EXTENSION IF EXISTS unaccent')
