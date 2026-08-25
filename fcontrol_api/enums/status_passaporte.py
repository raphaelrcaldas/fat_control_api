from enum import Enum


class StatusPassaporteEnum(str, Enum):
    """Situação do passaporte *físico* (lista fechada).

    Não descreve a validade do documento (isso são as datas), e sim onde o
    caderno está e se a seção pode contar com ele: arquivado e pronto para
    uso, em poder do militar na rotina, fora com o militar a serviço, ou
    fora da unidade por causa de renovação/expedição.
    """

    DISPONIVEL = 'disponivel'
    MILITAR = 'militar'
    MISSAO = 'missao'
    RENOVACAO = 'renovacao'
