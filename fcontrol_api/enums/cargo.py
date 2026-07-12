from enum import Enum


class CargoEnum(str, Enum):
    """Cargos institucionais que assinam documentos oficiais da org.

    Lista fechada e curada: cada valor vira uma linha de assinatura nos
    templates (rodape da Ordem de Missao, etc.). O titular de cada cargo
    e um `User` da propria org (FK), nunca texto livre — posto e nome sao
    derivados no momento da geracao do documento, de modo que promocao ou
    troca de titular se propaguem sozinhas.

    O rotulo impresso no documento mora em `CARGO_LABELS`.
    """

    COMANDANTE = 'comandante'
    CHEFE_OPERACOES = 'chefe-operacoes'


CARGO_LABELS: dict[CargoEnum, str] = {
    CargoEnum.COMANDANTE: 'Comandante',
    CargoEnum.CHEFE_OPERACOES: 'Operações',
}
