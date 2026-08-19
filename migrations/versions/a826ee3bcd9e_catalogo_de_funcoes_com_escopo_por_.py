"""catalogo de funcoes com escopo por unidade

Revision ID: a826ee3bcd9e
Revises: bbf8cfa798c7
Create Date: 2026-08-19 18:52:17.142426

Tira a lista de funcoes de tripulante do codigo (Literal no backend,
FUNCOES_CONFIG no client) e a transforma em dado: catalogo global
(`funcoes` + `funcoes_posicoes`) e conjunto operado por unidade
(`funcoes_uae`).

O seed reproduz exatamente o estado anterior do codigo, e `funcoes_uae` e
derivado dos dados que ja existem (funcoes distintas por org em
`tripulantes` e em `quads_func`), nao de um conjunto padrao cravado aqui.
Ambos rodam ANTES das FKs novas em `tripulantes.func` e `quads_func.func`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a826ee3bcd9e'
down_revision: Union[str, None] = 'bbf8cfa798c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (cod, nome, nome_curto, cor, ordem, esporadica) — ordem vem do FUNC_ORDER
# que vivia no client.
FUNCOES = [
    ('pil', 'Piloto', 'Piloto', 'blue', 1, False),
    ('oe', 'OE-3', 'OE-3', 'cyan', 2, False),
    ('mc', 'Mecânico', 'Mecânico', 'amber', 3, False),
    ('lm', 'Loadmaster', 'Loadmaster', 'emerald', 4, False),
    ('tf', 'Comissário', 'Comissário', 'purple', 5, False),
    ('os', 'Observador-SAR', 'Obs-SAR', 'red', 6, False),
    ('md', 'Médico', 'Médico', 'gray', 7, True),
    ('ml', 'Mestre de Lançamento', 'ML', 'pink', 8, True),
]

# (func_cod, cod, nome, descricao, tipo, ordem)
POSICOES = [
    ('pil', '1P', '1º Piloto', 'Piloto em comando', 'titular', 1),
    ('pil', '2P', '2º Piloto', 'Copiloto', 'titular', 2),
    ('pil', 'IN', 'Instrutor', 'Piloto instrutor', 'instrutor', 3),
    ('pil', 'AL', 'Aluno', 'Piloto em instrução', 'aluno', 4),
    ('pil', 'O3', 'OE-3', 'OE-3', 'titular', 5),
    ('oe', 'O3', 'Operador', 'OE-3 operacional', 'titular', 1),
    ('oe', 'I3', 'Instrutor', 'OE instrutor', 'instrutor', 2),
    ('oe', 'A3', 'Aluno', 'OE em instrução', 'aluno', 3),
    ('mc', 'MC', 'Mecânico', 'Mecânico', 'titular', 1),
    ('mc', 'IC', 'Instrutor', 'Mecânico instrutor', 'instrutor', 2),
    ('mc', 'AC', 'Aluno', 'Mecânico em instrução', 'aluno', 3),
    ('lm', 'LM', 'Loadmaster', 'Loadmaster titular', 'titular', 1),
    ('lm', 'IG', 'Instrutor', 'Loadmaster instrutor', 'instrutor', 2),
    ('lm', 'AG', 'Aluno', 'Loadmaster em instrução', 'aluno', 3),
    ('tf', 'TF', 'Comissário', 'Comissário titular', 'titular', 1),
    ('tf', 'IF', 'Instrutor', 'Comissário instrutor', 'instrutor', 2),
    ('tf', 'AF', 'Aluno', 'Comissário em instrução', 'aluno', 3),
    ('os', 'OS', 'Observador-SAR', 'Observador SAR', 'titular', 1),
    ('os', 'IS', 'Instrutor', 'Observador-SAR instrutor', 'instrutor', 2),
    ('os', 'AS', 'Aluno', 'Observador-SAR em instrução', 'aluno', 3),
]


def upgrade() -> None:
    op.create_table('funcoes',
    sa.Column('cod', sa.String(length=3), nullable=False),
    sa.Column('nome', sa.String(length=40), nullable=False),
    sa.Column('nome_curto', sa.String(length=20), nullable=False),
    sa.Column('cor', sa.String(length=16), nullable=False),
    sa.Column('ordem', sa.SmallInteger(), nullable=False),
    sa.Column('esporadica', sa.Boolean(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('cod')
    )
    op.create_table('funcoes_posicoes',
    sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
    sa.Column('func_cod', sa.String(length=3), nullable=False),
    sa.Column('cod', sa.String(length=2), nullable=False),
    sa.Column('nome', sa.String(length=40), nullable=False),
    sa.Column('ordem', sa.SmallInteger(), nullable=False),
    sa.Column('tipo', sa.String(length=10), nullable=False),
    sa.Column('descricao', sa.String(length=80), nullable=True),
    sa.ForeignKeyConstraint(['func_cod'], ['funcoes.cod'], onupdate='CASCADE', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('func_cod', 'cod', name='uq_funcoes_posicoes_func')
    )
    op.create_table('funcoes_uae',
    sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
    sa.Column('uae', sa.String(length=20), nullable=False),
    sa.Column('func_cod', sa.String(length=3), nullable=False),
    sa.Column('nome_custom', sa.String(length=40), nullable=True),
    sa.Column('ordem', sa.SmallInteger(), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['func_cod'], ['funcoes.cod'], onupdate='CASCADE', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['uae'], ['tenants.organizacao_id'], onupdate='CASCADE', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('uae', 'func_cod', name='uq_funcoes_uae_uae_func')
    )

    op.bulk_insert(
        sa.table(
            'funcoes',
            sa.column('cod', sa.String),
            sa.column('nome', sa.String),
            sa.column('nome_curto', sa.String),
            sa.column('cor', sa.String),
            sa.column('ordem', sa.SmallInteger),
            sa.column('esporadica', sa.Boolean),
            sa.column('active', sa.Boolean),
        ),
        [
            {
                'cod': cod,
                'nome': nome,
                'nome_curto': curto,
                'cor': cor,
                'ordem': ordem,
                'esporadica': esporadica,
                'active': True,
            }
            for cod, nome, curto, cor, ordem, esporadica in FUNCOES
        ],
    )
    op.bulk_insert(
        sa.table(
            'funcoes_posicoes',
            sa.column('func_cod', sa.String),
            sa.column('cod', sa.String),
            sa.column('nome', sa.String),
            sa.column('descricao', sa.String),
            sa.column('tipo', sa.String),
            sa.column('ordem', sa.SmallInteger),
        ),
        [
            {
                'func_cod': func_cod,
                'cod': cod,
                'nome': nome,
                'descricao': descricao,
                'tipo': tipo,
                'ordem': ordem,
            }
            for func_cod, cod, nome, descricao, tipo, ordem in POSICOES
        ],
    )

    # Rede de seguranca: se o banco tiver algum `func` fora do catalogo (o
    # campo era String(3) solto), ele entra como inativo em vez de derrubar
    # a FK criada no fim.
    op.execute("""
        INSERT INTO funcoes (cod, nome, nome_curto, cor, ordem, esporadica,
                             active)
        SELECT DISTINCT t.func, upper(t.func), upper(t.func), 'gray', 99,
                        false, false
        FROM tripulantes t
        WHERE t.func IS NOT NULL
        ON CONFLICT (cod) DO NOTHING
    """)
    op.execute("""
        INSERT INTO funcoes (cod, nome, nome_curto, cor, ordem, esporadica,
                             active)
        SELECT DISTINCT qf.func, upper(qf.func), upper(qf.func), 'gray', 99,
                        false, false
        FROM quads_func qf
        WHERE qf.func IS NOT NULL
        ON CONFLICT (cod) DO NOTHING
    """)

    # Conjunto operado por unidade derivado do que ja existe: funcoes dos
    # tripulantes da org, mais as funcoes usadas nos quadros dela.
    op.execute("""
        INSERT INTO funcoes_uae (uae, func_cod, active)
        SELECT DISTINCT t.uae, t.func, true
        FROM tripulantes t
        WHERE t.uae IS NOT NULL AND t.func IS NOT NULL
        ON CONFLICT (uae, func_cod) DO NOTHING
    """)
    op.execute("""
        INSERT INTO funcoes_uae (uae, func_cod, active)
        SELECT DISTINCT qg.uae, qf.func, true
        FROM quads_func qf
        JOIN quads_type qt ON qt.id = qf.type_id
        JOIN quads_group qg ON qg.id = qt.group_id
        WHERE qg.uae IS NOT NULL AND qf.func IS NOT NULL
        ON CONFLICT (uae, func_cod) DO NOTHING
    """)

    op.create_foreign_key('fk_quads_func_func', 'quads_func', 'funcoes', ['func'], ['cod'], onupdate='CASCADE')
    op.create_foreign_key('fk_tripulantes_func', 'tripulantes', 'funcoes', ['func'], ['cod'], onupdate='CASCADE')


def downgrade() -> None:
    op.drop_constraint('fk_tripulantes_func', 'tripulantes', type_='foreignkey')
    op.drop_constraint('fk_quads_func_func', 'quads_func', type_='foreignkey')
    op.drop_table('funcoes_uae')
    op.drop_table('funcoes_posicoes')
    op.drop_table('funcoes')
