"""funcao unica no tripulante (1:1)

Revision ID: 933dd913724d
Revises: 73d561516514
Create Date: 2026-07-09 15:07:47.078180

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '933dd913724d'
down_revision: Union[str, None] = '73d561516514'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Colunas de função adicionadas primeiro como nullable para permitir
    #    a cópia dos dados de trip_funcs antes de impor NOT NULL.
    op.add_column('tripulantes', sa.Column('func', sa.String(length=3), nullable=True))
    op.add_column('tripulantes', sa.Column('oper', sa.String(length=2), nullable=True))
    op.add_column('tripulantes', sa.Column('proj', sa.String(length=20), nullable=True))
    op.add_column('tripulantes', sa.Column('data_op', sa.Date(), nullable=True))

    # 2. Migração 1:1 — copia a (única) função de cada tripulante. DISTINCT ON
    #    garante determinismo caso houvesse mais de uma (mantém o menor id).
    op.execute(
        """
        UPDATE tripulantes t
        SET func = tf.func,
            oper = tf.oper,
            proj = tf.proj,
            data_op = tf.data_op
        FROM (
            SELECT DISTINCT ON (trip_id) trip_id, func, oper, proj, data_op
            FROM trip_funcs
            ORDER BY trip_id, id
        ) tf
        WHERE tf.trip_id = t.id
        """
    )

    # 3. Impõe NOT NULL agora que os dados foram copiados.
    op.alter_column('tripulantes', 'func', nullable=False)
    op.alter_column('tripulantes', 'oper', nullable=False)
    op.alter_column('tripulantes', 'proj', nullable=False)

    op.create_foreign_key('fk_tripulantes_proj', 'tripulantes', 'projetos_anvs', ['proj'], ['modelo'], onupdate='CASCADE')

    # 4. Tabela antiga deixa de existir.
    op.drop_table('trip_funcs')


def downgrade() -> None:
    op.create_table('trip_funcs',
    sa.Column('id', sa.INTEGER(), sa.Identity(always=False, start=1, increment=1, minvalue=1, maxvalue=2147483647, cycle=False, cache=1), autoincrement=True, nullable=False),
    sa.Column('trip_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('func', sa.VARCHAR(length=3), autoincrement=False, nullable=False),
    sa.Column('oper', sa.VARCHAR(length=2), autoincrement=False, nullable=False),
    sa.Column('proj', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('data_op', sa.DATE(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['proj'], ['projetos_anvs.modelo'], name=op.f('fk_trip_funcs_proj'), onupdate='CASCADE'),
    sa.ForeignKeyConstraint(['trip_id'], ['tripulantes.id'], name=op.f('trip_funcs_trip_id_fkey')),
    sa.PrimaryKeyConstraint('id', name=op.f('trip_funcs_pkey'))
    )

    # Restaura os dados de função de volta para trip_funcs.
    op.execute(
        """
        INSERT INTO trip_funcs (trip_id, func, oper, proj, data_op)
        SELECT id, func, oper, proj, data_op
        FROM tripulantes
        """
    )

    op.drop_constraint('fk_tripulantes_proj', 'tripulantes', type_='foreignkey')
    op.drop_column('tripulantes', 'data_op')
    op.drop_column('tripulantes', 'proj')
    op.drop_column('tripulantes', 'oper')
    op.drop_column('tripulantes', 'func')
