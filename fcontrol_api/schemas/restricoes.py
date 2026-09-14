from datetime import date
from typing import Literal

from pydantic import BaseModel

RestricaoOrigem = Literal['cemal', 'recencia_voo', 'operacao']
RestricaoCodigo = Literal[
    'cemal_ausente',
    'cemal_vencido',
    'desadaptacao',
    'operacao',
]
RestricaoEfeito = Literal['bloqueio', 'aviso']


class RestricaoDerivada(BaseModel):
    origem: RestricaoOrigem
    codigo: RestricaoCodigo
    inicio: date | None = None
    fim: date | None = None
    efeito: RestricaoEfeito
    # Só a restrição de operação preenche: a faixa precisa dizer QUAL operação
    # levou o militar, senão vira um bloqueio sem causa visível. As restrições
    # de CEMAL e recência se explicam pelo próprio código.
    rotulo: str | None = None
    operacao_id: int | None = None
