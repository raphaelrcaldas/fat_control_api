"""Seed data para soldos.

Valores de soldo por posto/graduacao.
Dados extraidos do Supabase em 2026-01-31.
"""

from datetime import date

from fcontrol_api.models.public.posto_grad import Soldo

# Soldos vigentes a partir de 2026-01-01
SOLDOS_DATA = [
    # (pg, valor, data_inicio, data_fim)
    ('1s', 5988.00, date(2026, 1, 1), None),
    ('1t', 9004.00, date(2026, 1, 1), None),
    ('2s', 5209.00, date(2026, 1, 1), None),
    ('2t', 8179.00, date(2026, 1, 1), None),
    ('3s', 4177.00, date(2026, 1, 1), None),
    ('as', 7988.00, date(2026, 1, 1), None),
    ('br', 13639.00, date(2026, 1, 1), None),
    ('cb', 2869.00, date(2026, 1, 1), None),
    ('cl', 12505.00, date(2026, 1, 1), None),
    ('cp', 9976.00, date(2026, 1, 1), None),
    ('mb', 14100.00, date(2026, 1, 1), None),
    ('mj', 12108.00, date(2026, 1, 1), None),
    ('s1', 2103.00, date(2026, 1, 1), None),
    ('s2', 1927.00, date(2026, 1, 1), None),
    ('so', 6737.00, date(2026, 1, 1), None),
    ('tc', 12285.00, date(2026, 1, 1), None),
]

SOLDOS = [
    Soldo(pg=pg, valor=valor, data_inicio=data_inicio, data_fim=data_fim)
    for pg, valor, data_inicio, data_fim in SOLDOS_DATA
]
