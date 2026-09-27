from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from fcontrol_api.enums.feedback import (
    FeedbackEventoTipoEnum,
    FeedbackStatusEnum,
    FeedbackTipoEnum,
)

# Mesmo teto do texto de abertura (`descricao`). `strip` antes do mínimo:
# mensagem só de espaços é 422, nunca um balão vazio.
TextoMensagem = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
]


class FeedbackUserOut(BaseModel):
    """Identificação mínima de quem enviou/escreveu.

    Não reusa `UserPublic` de propósito: aquele arrasta `posto` e o
    histórico de promoções (dois selectin por linha) para exibir um nome
    no topo de um balão.
    """

    id: int
    p_g: str
    nome_guerra: str

    model_config = ConfigDict(from_attributes=True)


class FeedbackCreate(BaseModel):
    tipo: FeedbackTipoEnum
    titulo: str = Field(min_length=3, max_length=120)
    descricao: str = Field(min_length=10, max_length=2000)
    rota: str | None = Field(default=None, max_length=120)


class FeedbackUpdate(BaseModel):
    """Mudança de status pela administração.

    A resposta saiu daqui: o que a administração diz ao autor é mensagem
    da conversa (`POST /admin/feedbacks/{id}/mensagens`).
    """

    status: FeedbackStatusEnum


class FeedbackMensagemCreate(BaseModel):
    texto: TextoMensagem


class FeedbackAdminMensagemCreate(FeedbackMensagemCreate):
    """Mensagem da administração, com troca de status opcional na mesma
    ação ("Enviar e marcar como Concluído")."""

    status: FeedbackStatusEnum | None = None


class FeedbackEventoOut(BaseModel):
    """Item da linha do tempo.

    `do_autor` é derivado no backend (`autor_id == feedback.user_id`):
    os dois fronts decidem o lado do balão por ele, sem comparar ids.
    `autor` nulo = administrador que saiu do sistema.
    """

    id: int
    tipo: FeedbackEventoTipoEnum
    texto: str | None = None
    status: FeedbackStatusEnum | None = None
    autor: FeedbackUserOut | None = None
    do_autor: bool
    created_at: datetime


class FeedbackBaseOut(BaseModel):
    id: int
    user_id: int
    uae: str
    tipo: FeedbackTipoEnum
    titulo: str
    descricao: str
    rota: str | None = None
    status: FeedbackStatusEnum
    origem: str
    created_at: datetime
    autor: FeedbackUserOut

    model_config = ConfigDict(from_attributes=True)


class FeedbackOut(FeedbackBaseOut):
    """Item de lista: o feedback e o resumo da conversa, sem ela."""

    total_mensagens: int
    ultima_mensagem: FeedbackEventoOut | None = None
    # Última MENSAGEM (ou o envio, sem mensagem). Mudança de status não
    # conta: a lista sobe quem recebeu algo para ler.
    ultima_atividade: datetime


class FeedbackDetalheOut(FeedbackOut):
    eventos: list[FeedbackEventoOut]
