"""EXCLUDE sem sobreposicao de vigencia em soldos e valor_diarias (btree_gist)

Revision ID: 91af20b1cca2
Revises: 9c9889308c66
Create Date: 2026-06-28 14:09:39.904366

Defesa em profundidade contra faixas de vigencia sobrepostas: cada faixa e o
intervalo inclusivo [data_inicio, data_fim] (data_fim NULL = aberta). Duas
faixas com a mesma chave (soldos: `pg`; valor_diarias: grupo_pg + grupo_cid)
nao podem se sobrepor, sob pena de o valor pago por dia ficar
nao-deterministico. A constraint e DEFERRABLE INITIALLY DEFERRED para permitir
o "auto-close" do periodo anterior (fecha o aberto e insere o novo) dentro da
mesma transacao.

ATENCAO (producao): se a base ja tiver faixas sobrepostas, o ADD CONSTRAINT
falha. Rodar antes a query de deteccao de overlaps e sanear os dados.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '91af20b1cca2'
down_revision: Union[str, None] = '9c9889308c66'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS btree_gist')

    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_soldos_sem_sobreposicao'
            ) THEN
                ALTER TABLE soldos
                    ADD CONSTRAINT ck_soldos_sem_sobreposicao
                    EXCLUDE USING gist (
                        pg WITH =,
                        daterange(data_inicio, data_fim, '[]') WITH &&
                    ) DEFERRABLE INITIALLY DEFERRED;
            END IF;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_valor_diarias_sem_sobreposicao'
            ) THEN
                ALTER TABLE cegep.valor_diarias
                    ADD CONSTRAINT ck_valor_diarias_sem_sobreposicao
                    EXCLUDE USING gist (
                        grupo_pg WITH =,
                        grupo_cid WITH =,
                        daterange(data_inicio, data_fim, '[]') WITH &&
                    ) DEFERRABLE INITIALLY DEFERRED;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute(
        'ALTER TABLE cegep.valor_diarias '
        'DROP CONSTRAINT IF EXISTS ck_valor_diarias_sem_sobreposicao'
    )
    op.execute(
        'ALTER TABLE soldos '
        'DROP CONSTRAINT IF EXISTS ck_soldos_sem_sobreposicao'
    )
    # A extensao btree_gist e mantida de proposito (pode ser usada por outras
    # constraints); remove-la aqui seria destrutivo se ja existia antes.
