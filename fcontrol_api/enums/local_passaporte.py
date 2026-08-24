from enum import Enum


class LocalPassaporteEnum(str, Enum):
    """Onde está o passaporte *físico* (lista fechada).

    Não descreve a validade do documento (isso são as datas), e sim a
    custódia do caderno: arquivado na seção, em poder do próprio militar,
    ou fora da unidade por causa de renovação/expedição.
    """

    SECAO = 'secao'
    MILITAR = 'militar'
    RENOVACAO = 'renovacao'
