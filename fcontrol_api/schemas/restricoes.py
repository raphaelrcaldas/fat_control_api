from datetime import date
from typing import Literal

from pydantic import BaseModel

RestricaoOrigem = Literal['cemal', 'recencia_voo']
RestricaoCodigo = Literal['cemal_ausente', 'cemal_vencido', 'desadaptacao']
RestricaoEfeito = Literal['bloqueio', 'aviso']


class RestricaoDerivada(BaseModel):
    origem: RestricaoOrigem
    codigo: RestricaoCodigo
    inicio: date | None = None
    fim: date | None = None
    efeito: RestricaoEfeito
