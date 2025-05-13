"""grupos diarias, cidades, pg

Revision ID: 1aa666b664a7
Revises: 9593da351421
Create Date: 2025-05-13 19:45:16.316835

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1aa666b664a7'
down_revision: Union[str, None] = '9593da351421'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("create schema cegep")

    op.create_table('grupos_pg',
    sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
    sa.Column('grupo', sa.Integer(), nullable=False),
    sa.Column('pg_short', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['pg_short'], ['posto_grad.short'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='cegep'
    )
    op.create_table('grupos_cidade',
    sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
    sa.Column('grupo', sa.Integer(), nullable=False),
    sa.Column('cidade_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['cidade_id'], ['cidades.codigo'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='cegep'
    )
    op.create_table('valor_diarias',
    sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
    sa.Column('grupo_pg', sa.Integer(), nullable=False),
    sa.Column('grupo_cid', sa.Integer(), nullable=False),
    sa.Column('valor', sa.Float(), nullable=False),
    sa.Column('data_inicio', sa.Date(), nullable=False),
    sa.Column('data_fim', sa.Date(), nullable=True),
    sa.ForeignKeyConstraint(['grupo_cid'], ['cegep.grupos_cidade.id'], ),
    sa.ForeignKeyConstraint(['grupo_pg'], ['cegep.grupos_pg.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='cegep'
    )
    op.create_unique_constraint(None, 'indisps', ['id'])
    op.create_unique_constraint(None, 'posto_grad', ['short'])
    op.create_unique_constraint(None, 'quad', ['id'])
    op.create_unique_constraint(None, 'quads_func', ['id'])
    op.create_unique_constraint(None, 'quads_group', ['id'])
    op.create_unique_constraint(None, 'quads_type', ['id'])
    op.create_unique_constraint(None, 'trip_funcs', ['id'])
    op.create_unique_constraint(None, 'tripulantes', ['id'])
    op.create_unique_constraint(None, 'users', ['id'])
    op.create_unique_constraint(None, 'permissions', ['id'], schema='security')
    op.create_unique_constraint(None, 'resources', ['id'], schema='security')
    op.create_unique_constraint(None, 'role_permissions', ['id'], schema='security')
    op.create_unique_constraint(None, 'roles', ['id'], schema='security')
    op.create_unique_constraint(None, 'user_roles', ['id'], schema='security')


def downgrade() -> None:
    op.drop_constraint(None, 'user_roles', schema='security', type_='unique')
    op.drop_constraint(None, 'roles', schema='security', type_='unique')
    op.drop_constraint(None, 'role_permissions', schema='security', type_='unique')
    op.drop_constraint(None, 'resources', schema='security', type_='unique')
    op.drop_constraint(None, 'permissions', schema='security', type_='unique')
    op.drop_constraint(None, 'users', type_='unique')
    op.drop_constraint(None, 'tripulantes', type_='unique')
    op.drop_constraint(None, 'trip_funcs', type_='unique')
    op.drop_constraint(None, 'quads_type', type_='unique')
    op.drop_constraint(None, 'quads_group', type_='unique')
    op.drop_constraint(None, 'quads_func', type_='unique')
    op.drop_constraint(None, 'quad', type_='unique')
    op.drop_constraint(None, 'posto_grad', type_='unique')
    op.drop_constraint(None, 'indisps', type_='unique')
    op.drop_table('valor_diarias', schema='cegep')
    op.drop_table('grupos_cidade', schema='cegep')
    op.drop_table('grupos_pg', schema='cegep')

    op.execute("drop schema security")

