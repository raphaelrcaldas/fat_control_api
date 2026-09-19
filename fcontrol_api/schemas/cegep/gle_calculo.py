"""Forma da apuração de GLE exibida ao usuário.

A memória de cálculo é a mesma para toda leitura de missão salva: o
backend recalcula a partir dos trechos e do soldo vigente, e estes
schemas descrevem o que sai. Ver `docs/dominio/gle.md`.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class DiaCalculado(BaseModel):
    data: date
    horas: Decimal
    fator: Decimal
    # Dia que caiu na antisobreposição: aparece na memória de cálculo com
    # fator zero, para o usuário ver que foi considerado e por quê.
    duplicado: bool


class TrechoCalculado(BaseModel):
    loc_esp_id: int
    cidade: str
    uf: str
    grupo: int
    chegada: datetime
    afastamento: datetime
    dias_contados: int
    multiplicador: Decimal
    dias: list[DiaCalculado]
