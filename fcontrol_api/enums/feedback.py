from enum import Enum


class FeedbackTipoEnum(str, Enum):
    """Natureza do que o usuário mandou pelo portal."""

    BUG = 'bug'
    SUGESTAO = 'sugestao'
    DUVIDA = 'duvida'
    ELOGIO = 'elogio'
    DESABAFO = 'desabafo'


class FeedbackStatusEnum(str, Enum):
    """Ciclo de vida do feedback, do envio ao desfecho.

    `ABERTO` é o estado inicial (quem envia não escolhe status). Os
    demais são atribuídos pela administração de sistema, e `RECUSADO` /
    `CONCLUIDO` são terminais — o portal os apresenta como resolvidos.
    """

    ABERTO = 'aberto'
    EM_ANALISE = 'em_analise'
    ACEITO = 'aceito'
    RECUSADO = 'recusado'
    CONCLUIDO = 'concluido'


# Estados em que a conversa fica só leitura para o autor: o item está
# resolvido, e sem sinal para a administração uma mensagem nova ali
# passaria despercebida. A administração ainda escreve e pode reabrir.
STATUS_ENCERRADOS = frozenset({
    FeedbackStatusEnum.CONCLUIDO.value,
    FeedbackStatusEnum.RECUSADO.value,
})


class FeedbackEventoTipoEnum(str, Enum):
    """O que um item da conversa do feedback registra.

    `MENSAGEM` é texto de alguém (autor ou administração); `STATUS` é a
    mudança de estado, que entra na linha do tempo para o autor entender o
    que aconteceu e quando.
    """

    MENSAGEM = 'mensagem'
    STATUS = 'status'
