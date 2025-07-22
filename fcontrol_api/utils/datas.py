from datetime import date, datetime, timedelta
from typing import List


def listar_datas_entre(inicio: datetime, fim: datetime) -> List[date]:
    data_inicio = inicio.date()
    data_fim = fim.date()
    if data_fim < data_inicio:
        return []
    return [
        data_inicio + timedelta(days=i)
        for i in range((data_fim - data_inicio).days + 1)
    ]
