from enum import Enum


class FeedbackTipoEnum(str, Enum):
    """Natureza do que o usuário mandou pelo portal."""

    BUG = 'bug'
    SUGESTAO = 'sugestao'
    DUVIDA = 'duvida'
    ELOGIO = 'elogio'


class FeedbackStatusEnum(str, Enum):
    """Ciclo de vida do feedback, do envio ao desfecho.

    `ABERTO` é o estado inicial (quem envia não escolhe status). Os
    demais são atribuídos pela administração da unidade, e `RECUSADO` /
    `CONCLUIDO` são terminais — o portal os apresenta como resolvidos.
    """

    ABERTO = 'aberto'
    EM_ANALISE = 'em_analise'
    ACEITO = 'aceito'
    RECUSADO = 'recusado'
    CONCLUIDO = 'concluido'
