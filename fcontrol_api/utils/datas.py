from datetime import date, timedelta
from typing import List


def listar_datas_entre(inicio: date, fim: date) -> List[date]:
    if fim < inicio:
        return []
    return [inicio + timedelta(days=i) for i in range((fim - inicio).days + 1)]
