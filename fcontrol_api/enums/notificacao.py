from enum import StrEnum


class NotifEscopo(StrEnum):
    """Discriminador da notificação.

    `DIRETA` é endereçada a um usuário (`user_id`) e tem ciclo de leitura
    (`read_at`); `TAREFA` é endereçada a uma permissão (`req_resource` +
    `req_action`) e tem ciclo de resolução (`resolved_at`). Uma tabela só,
    para a lista sair ordenada por `created_at` sem UNION/merge.
    """

    DIRETA = 'direta'
    TAREFA = 'tarefa'


class NotifAudiencia(StrEnum):
    """Qual app enxerga a notificação.

    A segregação é imposta no backend pelo `app_client` do token (não por
    filtro de front): logado no client a pessoa só vê notificações de
    gestão; as de tripulante só aparecem no FatBird — mesmo sendo a mesma
    pessoa nos dois papéis, até porque os deep-links de um app não existem
    no outro.
    """

    TRIPULANTE = 'tripulante'
    GESTOR = 'gestor'


class NotifTipo(StrEnum):
    """Eventos que emitem notificação.

    Gravado como String no banco (não ENUM nativo): valor novo não pede
    migration — mesmo contrato de `feedbacks.tipo`.
    """

    QUADRO_RECEBIDO = 'quadro.recebido'
    QUADRO_REMOVIDO = 'quadro.removido'
