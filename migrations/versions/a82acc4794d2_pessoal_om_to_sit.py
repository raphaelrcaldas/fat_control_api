"""pessoal om to sit

Revision ID: a82acc4794d2
Revises: 92ca7c6d7cce
Create Date: 2026-06-10 22:21:25.055788

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a82acc4794d2'
down_revision: Union[str, None] = '92ca7c6d7cce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'operacao_pessoal',
        sa.Column('sit', sa.String(length=1), nullable=False),
    )
    op.alter_column(
        'operacao_pessoal',
        'func',
        existing_type=sa.VARCHAR(length=80),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
    op.drop_column('operacao_pessoal', 'om')
    # CHECK constraints não são detectados pelo autogenerate.
    op.create_check_constraint(
        'ck_operacao_pessoal_func',
        'operacao_pessoal',
        "func IN ('Tripulante', 'Apoio', 'Manutenção')",
    )
    op.create_check_constraint(
        'ck_operacao_pessoal_sit',
        'operacao_pessoal',
        "sit IN ('d', 'g', 'c')",
    )


def downgrade() -> None:
    op.drop_constraint(
        'ck_operacao_pessoal_sit', 'operacao_pessoal', type_='check'
    )
    op.drop_constraint(
        'ck_operacao_pessoal_func', 'operacao_pessoal', type_='check'
    )
    op.add_column(
        'operacao_pessoal',
        sa.Column(
            'om',
            sa.VARCHAR(length=60),
            autoincrement=False,
            nullable=False,
        ),
    )
    op.alter_column(
        'operacao_pessoal',
        'func',
        existing_type=sa.String(length=20),
        type_=sa.VARCHAR(length=80),
        existing_nullable=False,
    )
    op.drop_column('operacao_pessoal', 'sit')
