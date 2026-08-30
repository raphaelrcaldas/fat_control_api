from datetime import datetime

from pydantic import BaseModel, ConfigDict

from fcontrol_api.enums.notificacao import NotifAudiencia, NotifEscopo


class NotificacaoOut(BaseModel):
    """Item da lista de notificações (diretas e tarefas juntas).

    `tipo` sai como str cru (não `NotifTipo`): o backend pode emitir um
    tipo novo antes do front conhecê-lo, e o item ainda deve serializar —
    o front trata tipo desconhecido como notificação sem deep-link.
    """

    id: int
    uae: str
    escopo: NotifEscopo
    audiencia: NotifAudiencia
    tipo: str
    titulo: str
    descricao: str | None = None
    recurso: str
    recurso_id: int | None = None
    user_id: int | None = None
    read_at: datetime | None = None
    req_resource: str | None = None
    req_action: str | None = None
    resolved_by: int | None = None
    resolved_at: datetime | None = None
    payload: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificacaoContador(BaseModel):
    """Contadores do sino: diretas não lidas + tarefas abertas visíveis."""

    nao_lidas: int
    tarefas: int
    total: int
