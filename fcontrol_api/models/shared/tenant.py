from datetime import datetime

from sqlalchemy import ForeignKey, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .organizacao import Organizacao


class Tenant(Base):
    """Organização que é cliente da plataforma (tenant ativo).

    Subconjunto de `organizacoes`: a PK é compartilhada com o diretório
    universal (`organizacao_id` é PK e FK ao mesmo tempo). Apenas orgs
    registradas aqui podem ter vínculos de perfil/escopo na plataforma.
    """

    __tablename__ = 'tenants'

    organizacao_id: Mapped[str] = mapped_column(
        ForeignKey(
            'organizacoes.sigla', ondelete='RESTRICT', onupdate='CASCADE'
        ),
        primary_key=True,
    )
    active: Mapped[bool] = mapped_column(
        init=False, default=True, server_default=text('true')
    )
    # Tema de cor de marca (TemaEnum). String livre no banco; a validação
    # contra a lista fechada mora no schema Pydantic. Default 'red' = tema
    # padrão do produto.
    tema: Mapped[str] = mapped_column(
        String(20), default='red', server_default=text("'red'")
    )
    created_at: Mapped[datetime] = mapped_column(
        init=False, server_default=func.now()
    )

    organizacao: Mapped[Organizacao] = relationship(
        Organizacao, lazy='selectin', init=False
    )
